"""Shared fixtures for agra CLI unit tests.

Tests never touch the real /etc/agra or run ansible-playbook: the paths the CLI
reads are redirected to tmp_path and ansible availability checks are stubbed.
"""
from __future__ import annotations

import pytest


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
