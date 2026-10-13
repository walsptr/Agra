"""CLI wiring and safety guards (RULES §8): destructive commands never reach Ansible without the flag."""
from __future__ import annotations

import argparse

import pytest

from agra.cli import build_parser, main


def _subcommands():
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return sorted(sub.choices)


@pytest.mark.parametrize("command", _subcommands())
def test_every_command_has_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([command, "--help"])
    assert exc.value.code == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    ["destroy"],
    ["destroy", "--purge-data"],
    ["destroy", "--purge-all"],
    ["restore", "-n", "agra-backup-20260101"],
    ["restore", "-f", "/tmp/agra-backup-20260101.tar.gz"],
])
def test_destructive_commands_blocked_without_confirmation_flag(argv, no_playbook_run, monkeypatch):
    monkeypatch.setenv("AGRA_NON_INTERACTIVE", "1")

    assert main(argv) != 0


@pytest.mark.parametrize("command", ["check", "precheck", "verify"])
def test_check_requires_explicit_inventory(command, no_playbook_run, monkeypatch):
    monkeypatch.delenv("AGRA_INVENTORY", raising=False)

    assert main([command]) != 0


def test_check_passes_cli_guard_var(monkeypatch, inventory_file):
    import agra.commands.check as check

    calls = []
    monkeypatch.setattr(check, "run_playbook", lambda name, **kw: calls.append((name, kw)) or 0)
    monkeypatch.setattr(check, "_warn_misplaced_globals_keys", lambda: None)

    assert main(["check", "-i", str(inventory_file)]) == 0
    name, kw = calls[0]
    assert name == "precheck"
    assert kw["extra_vars"]["_agra_cli_inventory_explicit_confirmed"] is True


def test_check_warns_about_globals_keys_that_no_longer_exist(tmp_path, monkeypatch):
    import agra.commands.check as check

    globals_file = tmp_path / "globals.yml"
    globals_file.write_text("grafana_nginx_port: 30080\nprometheus_nginx_port: 30090\nenable_https: true\n")
    warnings = []
    monkeypatch.setattr(check, "GLOBALS_FILE", globals_file)
    monkeypatch.setattr(check, "warn", warnings.append)

    check._warn_misplaced_globals_keys()

    assert [w for w in warnings if "grafana_nginx_port" in w]
    assert [w for w in warnings if "prometheus_nginx_port" in w]
    assert not [w for w in warnings if "enable_https" in w]


def test_genpwd_force_needs_confirmation(no_playbook_run):
    assert main(["genpwd", "--force"]) != 0


def test_genpwd_force_confirmed_is_passed_to_the_playbook(monkeypatch):
    import agra.commands.genpwd as genpwd

    calls = []
    monkeypatch.setattr(genpwd, "run_playbook", lambda name, **kw: calls.append((name, kw)) or 0)

    assert main(["genpwd", "--force", "--yes-i-really-mean-it"]) == 0
    assert calls[0][1]["extra_vars"] == {"genpwd_force": True, "genpwd_confirm": True}


def test_genpwd_does_not_invent_third_party_credentials():
    # A random value passes precheck but never matches what the DBA or the
    # S3 provider issued (PR 21: grafana_database_password).
    import yaml

    from agra.constants import PLAYBOOK_DIR

    play = yaml.safe_load((PLAYBOOK_DIR / "genpwd.yml").read_text())[0]
    generated = {f["key"] for f in play["vars"]["genpwd_fields"]}
    operator = {f["key"] for f in play["vars"]["genpwd_operator_fields"]}
    third_party = {"grafana_database_password", "backup_s3_access_key", "backup_s3_secret_key"}
    assert not generated & third_party
    assert operator == third_party
