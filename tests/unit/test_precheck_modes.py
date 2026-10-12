"""Precheck modes (PR 13): only `agra check` bootstraps nodes (apt/dnf upgrade,
Docker install). backup/upgrade/rollback/restore validate only, on the hosts
they target, and never touch a node before the operator has confirmed."""
from __future__ import annotations

import builtins

import pytest
import yaml

from agra.cli import main
from agra.constants import PLAYBOOK_DIR


@pytest.fixture
def backup_dir(tmp_path):
    for name in ("agra-backup-20261001T010000",):
        (tmp_path / f"{name}.yml").write_text(f"backup_name: {name}\n")
        (tmp_path / f"{name}.tar.gz").write_bytes(b"x")
    return tmp_path


@pytest.fixture
def calls(monkeypatch, etc_agra):
    """Every run_playbook call, in order, from check.py and the wrapper modules."""
    import agra.commands.backup as backup
    import agra.commands.check as check
    import agra.commands.restore as restore
    import agra.commands.rollback as rollback
    import agra.commands.upgrade as upgrade

    seen = []
    for mod in (check, backup, upgrade, rollback, restore):
        monkeypatch.setattr(mod, "run_playbook", lambda name, **kw: seen.append((name, kw)) or 0)
    monkeypatch.setattr(rollback, "load_installed_versions", lambda: {
        "current": {"versions": {"grafana_tag": "11.3.0"}},
        "previous": {"versions": {"grafana_tag": "11.2.0"}},
    })
    monkeypatch.delenv("AGRA_INVENTORY", raising=False)
    return seen


def _wrappers(inv, bdir):
    return {
        "backup": ["backup", "create", "-i", inv],
        "upgrade": ["upgrade", "-i", inv],
        "rollback": ["rollback", "-i", inv, "--yes"],
        "restore": ["restore", "-i", inv, "-n", "agra-backup-20261001T010000", "-d", bdir,
                    "--yes-i-really-mean-it", "--yes"],
    }


@pytest.mark.parametrize("command", ["backup", "upgrade", "rollback", "restore"])
def test_wrappers_run_precheck_without_bootstrap(command, calls, inventory_file, backup_dir):
    assert main(_wrappers(str(inventory_file), str(backup_dir))[command]) == 0

    name, kw = calls[0]
    assert name == "precheck"
    assert kw["extra_vars"]["_agra_precheck_bootstrap"] is False
    assert "_agra_precheck_limit" not in kw["extra_vars"]
    assert len(calls) >= 2 and calls[-1][0] != "precheck"


@pytest.mark.parametrize("command", ["backup", "upgrade", "rollback", "restore"])
def test_wrappers_precheck_only_the_limited_hosts(command, calls, inventory_file, backup_dir):
    argv = _wrappers(str(inventory_file), str(backup_dir))[command] + ["-l", "monitoring:!mon1"]

    assert main(argv) == 0

    name, kw = calls[0]
    # A pattern, not --limit: --limit would also skip the validation play on localhost.
    assert kw["extra_vars"]["_agra_precheck_limit"] == "monitoring:!mon1"
    assert kw.get("limit") is None


def test_agra_check_still_bootstraps(calls, inventory_file):
    assert main(["check", "-i", str(inventory_file)]) == 0

    name, kw = calls[0]
    assert name == "precheck"
    assert "_agra_precheck_bootstrap" not in kw["extra_vars"]


@pytest.mark.parametrize("command", ["backup", "upgrade", "rollback", "restore", "check"])
def test_missing_inventory_is_an_operator_error_before_any_prompt(command, calls, backup_dir, monkeypatch, capsys):
    monkeypatch.setattr(builtins, "input", lambda *a: pytest.fail("prompted before checking -i"))
    argv = {
        "backup": ["backup", "create"],
        "upgrade": ["upgrade"],
        "rollback": ["rollback"],
        "restore": ["restore", "-n", "agra-backup-20261001T010000", "-d", str(backup_dir), "--yes-i-really-mean-it"],
        "check": ["check"],
    }[command]

    assert main(argv) == 2
    assert calls == []
    err = capsys.readouterr().err
    assert "-i <inventory>" in err and "--no-precheck" not in err


def test_restore_confirms_before_touching_any_node(calls, inventory_file, backup_dir, monkeypatch):
    monkeypatch.delenv("AGRA_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(builtins, "input", lambda *a: "no")

    rc = main(["restore", "-i", str(inventory_file), "-n", "agra-backup-20261001T010000", "-d", str(backup_dir),
               "--yes-i-really-mean-it"])

    assert rc == 1 and calls == []


def _walk(tasks, gated=False):
    for task in tasks or []:
        when = task.get("when", "")
        here = gated or "_pc_bootstrap" in (" ".join(when) if isinstance(when, list) else str(when))
        if "block" in task:
            yield from _walk(task["block"], here)
        else:
            yield task, here


MUTATING = {"ansible.builtin.apt", "ansible.builtin.dnf", "ansible.builtin.yum_repository",
            "ansible.builtin.service", "ansible.builtin.package", "ansible.builtin.systemd"}


def test_every_node_change_in_precheck_is_bootstrap_only():
    plays = yaml.safe_load((PLAYBOOK_DIR / "precheck.yml").read_text())
    tasks = [t for play in plays for t in _walk(play.get("tasks"))]
    mutating = [(t["name"], gated) for t, gated in tasks if MUTATING & set(t)]

    assert len(mutating) >= 6
    assert [name for name, gated in mutating if not gated] == []
