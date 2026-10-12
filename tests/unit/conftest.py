"""Shared fixtures for agra CLI unit tests.

Tests never touch the real /etc/agra or run ansible-playbook: the paths the CLI
reads are redirected to tmp_path and ansible availability checks are stubbed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agra.constants import PLAYBOOK_DIR, PROJECT_ROOT

ANSIBLE_PLAYBOOK = (shutil.which("ansible-playbook", path=str(Path(sys.executable).parent))
                    or shutil.which("ansible-playbook"))
needs_ansible = pytest.mark.skipif(ANSIBLE_PLAYBOOK is None, reason="needs ansible-playbook")

# Skips CI accepts: contexts/ and docs/ are not published (PR 12). With
# AGRA_STRICT_SKIPS=1 (CI) any other skip fails, so a missing tool or file
# cannot quietly turn a check off.
ALLOWED_SKIP = "not in this checkout"


def _strict_skip(report):
    if not (os.environ.get("AGRA_STRICT_SKIPS") and report.skipped) or hasattr(report, "wasxfail"):
        return
    reason = report.longrepr[-1] if isinstance(report.longrepr, tuple) else str(report.longrepr)
    if ALLOWED_SKIP not in reason:
        report.outcome = "failed"
        report.longrepr = f"skipped, and AGRA_STRICT_SKIPS allows only '{ALLOWED_SKIP}': {reason}"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    _strict_skip(outcome.get_result())


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    _strict_skip(outcome.get_result())


def run_playbook_locally(tmp_path, playbook: str, inventory: str, extra_vars: dict, *args: str):
    """Run a repo playbook for real, like the CLI does: the globals.yml
    template first, then extra_vars. Callers keep every task on localhost or
    on hosts with ansible_connection=local + ansible_become=false, with paths
    under tmp_path."""
    inv = tmp_path / "hosts.ini"
    inv.write_text(inventory)
    evars = tmp_path / "vars.json"
    evars.write_text(json.dumps(extra_vars))
    env = {**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "False", "ANSIBLE_NOCOLOR": "1",
           "ANSIBLE_LOCALHOST_WARNING": "False", "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
           # Modules run with this Python, not ansible.cfg's /usr/bin/python3
           # (absent on python:*-slim images, an older system Python elsewhere).
           "ANSIBLE_PYTHON_INTERPRETER": sys.executable,
           # ansible.cfg says become = True: never sudo from a unit test
           # (plays that set become themselves get ansible_become=false hosts).
           "ANSIBLE_BECOME": "False"}
    return subprocess.run(
        [ANSIBLE_PLAYBOOK, "-i", str(inv), "-e", f"@{PROJECT_ROOT / 'etc/agra/globals.yml'}", "-e", f"@{evars}",
         *args, str(PLAYBOOK_DIR / playbook)],
        capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=180, check=False,
    )


@pytest.fixture
def etc_agra(tmp_path, monkeypatch):
    """Fake /etc/agra with readable globals.yml + passwords.yml, wired into run_playbook."""
    etc = tmp_path / "etc-agra"
    etc.mkdir()
    globals_file = etc / "globals.yml"
    passwords_file = etc / "passwords.yml"
    globals_file.write_text("grafana_tag: '11.2.0'\n")
    passwords_file.write_text("grafana_admin_password: 'unit-test-password'\n")
    passwords_file.chmod(0o600)

    import agra.utils.run_playbook as rp

    monkeypatch.setattr(rp, "GLOBALS_FILE", globals_file)
    monkeypatch.setattr(rp, "PASSWORDS_FILE", passwords_file)
    monkeypatch.setattr(rp, "ETC_DIR", etc)
    monkeypatch.setattr(rp, "_check_ansible_available", lambda: None)
    return etc


@pytest.fixture
def inventory_file(tmp_path):
    """An existing inventory file outside the repo (absolute path)."""
    inv = tmp_path / "hosts.ini"
    inv.write_text("[monitoring]\nmon1 ansible_host=192.0.2.10\n")
    return inv


@pytest.fixture
def no_playbook_run(monkeypatch):
    """Make any attempt to run a playbook fail the test loudly.

    Command modules import run_playbook by name, so patch every module that does.
    """
    import importlib

    from agra.commands import COMMAND_MODULES

    def _forbidden(*args, **kwargs):
        raise AssertionError(f"run_playbook must not be called (args={args}, kwargs={kwargs})")

    for mod_name in COMMAND_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "run_playbook"):
            monkeypatch.setattr(mod, "run_playbook", _forbidden)
    return _forbidden
