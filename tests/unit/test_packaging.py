"""Packaging (PR 9): a non-editable install finds its playbooks, ships the
passwords template, and never ships an operator's passwords.yml."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

import yaml

import agra.constants as constants
from agra.constants import PLAYBOOK_DIR, PROJECT_ROOT as REPO_ROOT, SECRET_KEYS


def _data_files():
    """data_files from setup.py, run against a stub setuptools (not always installed)."""
    import types

    captured = {}
    stub = types.ModuleType("setuptools")
    stub.setup = lambda **kw: captured.update(kw)
    saved = sys.modules.get("setuptools")
    sys.modules["setuptools"] = stub
    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        runpy.run_path(str(REPO_ROOT / "setup.py"))
    finally:
        os.chdir(cwd)
        if saved is None:
            del sys.modules["setuptools"]
        else:
            sys.modules["setuptools"] = saved
    return {os.path.join(dest, os.path.basename(f)) for dest, files in captured["data_files"] for f in files}


def test_data_files_ship_playbooks_roles_config_and_templates():
    shipped = _data_files()

    for name in ("deploy.yml", "genpwd.yml", "precheck.yml"):
        assert f"share/agra/ansible/playbooks/{name}" in shipped
    assert "share/agra/ansible/roles/grafana/tasks/main.yml" in shipped
    assert "share/agra/ansible.cfg" in shipped
    assert "share/agra/inventory/all-in-one" in shipped
    assert "share/agra/etc/agra/globals.yml" in shipped
    assert "share/agra/etc/agra/passwords.yml.example" in shipped


def test_data_files_never_ship_a_real_passwords_file():
    shipped = _data_files()

    assert not any(p.endswith("/passwords.yml") or "passwords.yml.bak" in p for p in shipped)
    assert not any("__pycache__" in p for p in shipped)


def test_passwords_template_matches_genpwd_and_is_empty():
    template = yaml.safe_load((REPO_ROOT / "etc/agra/passwords.yml.example").read_text())
    play = yaml.safe_load((PLAYBOOK_DIR / "genpwd.yml").read_text())[0]
    genpwd_keys = [f["key"] for f in play["vars"]["genpwd_fields"]] + play["vars"]["genpwd_operator_fields"]

    assert list(template) == genpwd_keys
    assert set(template) == set(SECRET_KEYS)
    assert all(v == "" for v in template.values())


def test_installed_layout_resolves_share_agra(tmp_path, monkeypatch):
    # Simulate site-packages/agra/constants.py with data under <prefix>/share/agra.
    site = tmp_path / "lib" / "site-packages" / "agra"
    site.mkdir(parents=True)
    fake_constants = site / "constants.py"
    fake_constants.write_text(Path(constants.__file__).read_text())
    prefix = tmp_path / "prefix"
    (prefix / "share" / "agra" / "ansible" / "playbooks").mkdir(parents=True)

    import sysconfig
    monkeypatch.setattr(sysconfig, "get_path", lambda name, *a, **kw: str(prefix))
    ns = runpy.run_path(str(fake_constants))

    assert ns["PROJECT_ROOT"] == prefix / "share" / "agra"
    assert ns["PLAYBOOKS"]["deploy"] == prefix / "share" / "agra" / "ansible" / "playbooks" / "deploy.yml"


def test_ansible_from_agra_venv_comes_first(monkeypatch):
    from agra.utils.paths import ansible_env

    monkeypatch.setenv("PATH", "/nonexistent-a:/nonexistent-b")
    path = ansible_env()["PATH"].split(os.pathsep)

    assert path[0] == str(Path(sys.executable).parent)
    assert path[1:] == ["/nonexistent-a", "/nonexistent-b"]


def test_requirements_txt_matches_pyproject_dependencies():
    import re

    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    block = re.search(r"^dependencies = \[(.*?)\]", pyproject, re.M | re.S).group(1)
    declared = re.findall(r'"([^"]+)"', block)
    listed = [line.strip() for line in (REPO_ROOT / "requirements.txt").read_text().splitlines()
              if line.strip() and not line.startswith("#")]
    assert listed == declared
