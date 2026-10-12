"""CLI loose ends (PR 9): -e cannot override confirmed values, backup list --json,
tls regenerate --days, no dead destroy flags."""
from __future__ import annotations

import json

import pytest

from agra.cli import build_parser, main
from agra.utils.run_playbook import build_ansible_command


@pytest.mark.parametrize("argv", [
    # Rollback target shown in the plan must be what runs.
    ["rollback", "--yes", "-e", "grafana_tag=9.0.0"],
    ["rollback", "--yes", "--service", "grafana", "-e", '{"prometheus_tag": "v2.0.0"}'],
    # Purge only through --purge-* (shown in the warning), never -e.
    ["destroy", "--yes-i-really-mean-it", "-e", "destroy_purge_data=true"],
    ["destroy", "--yes-i-really-mean-it", "-e", "foo=1 destroy_purge_config=true"],
    ["restore", "-n", "x", "--yes-i-really-mean-it", "-e", "restore_local_tarball=/tmp/evil.tar.gz"],
    ["upgrade", "--grafana-tag", "11.3.0", "-e", "grafana_tag=12.0.0"],
])
def test_extra_vars_cannot_override_cli_controlled_vars(argv, no_playbook_run, monkeypatch, inventory_file, capsys):
    monkeypatch.setenv("AGRA_NON_INTERACTIVE", "1")

    assert main(argv[:1] + ["-i", str(inventory_file)] + argv[1:]) == 2
    assert "tidak boleh menimpa" in capsys.readouterr().err


def test_extra_vars_file_conflict_is_detected(no_playbook_run, monkeypatch, inventory_file, tmp_path):
    vars_file = tmp_path / "vars.yml"
    vars_file.write_text("destroy_purge_data: true\n")

    assert main(["destroy", "-i", str(inventory_file), "--yes-i-really-mean-it", "-e", f"@{vars_file}"]) == 2


def test_unrelated_extra_vars_still_pass(monkeypatch, inventory_file):
    import agra.commands.upgrade as upgrade

    calls = []
    monkeypatch.setattr(upgrade, "run_playbook", lambda name, **kw: calls.append((name, kw)) or 0)

    assert main(["upgrade", "-i", str(inventory_file), "--no-precheck", "-e", "grafana_tag=11.3.0"]) == 0
    assert "grafana_tag=11.3.0" in calls[-1][1]["extra_vars_raw"]


def test_cli_vars_come_after_user_extra_vars(etc_agra, inventory_file):
    # Last -e wins in Ansible: even an unparseable user -e cannot beat the CLI.
    argv, _ = build_ansible_command(
        "destroy", inventory=str(inventory_file),
        extra_vars={"destroy_purge_data": False},
        extra_vars_raw=["not parseable ' quote"],
    )

    values = [argv[i + 1] for i, a in enumerate(argv) if a in ("-e", "--extra-vars")]
    assert values[-1] == json.dumps({"destroy_purge_data": False})
    assert values.index("not parseable ' quote") < len(values) - 1


@pytest.mark.parametrize("flag", ["-y", "--yes", "--precheck", "--no-precheck"])
def test_destroy_has_no_dead_flags(flag):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["destroy", "--yes-i-really-mean-it", flag])
    assert exc.value.code == 2


def test_tls_regenerate_passes_days_and_cn(monkeypatch, inventory_file):
    import agra.commands.tls as tls

    seen = {}
    monkeypatch.setattr(tls.certificates, "_detect_custom", lambda g, c, k: (False, ""))
    monkeypatch.setattr(tls.certificates, "cmd_generate", lambda a: seen.update(days=a.days, cn=a.cn, force=a.force) or 0)
    monkeypatch.setattr(tls, "run_playbook", lambda name, **kw: 0)

    assert main(["tls", "-i", str(inventory_file), "regenerate", "-y", "--days", "90", "--cn", "mon.example"]) == 0
    assert seen == {"days": 90, "cn": "mon.example", "force": True}


def _write_backup(d, name, **fields):
    lines = [f"backup_name: {name}"] + [f"{k}: {v}" for k, v in fields.items()]
    (d / f"{name}.yml").write_text("\n".join(lines) + "\n")
    (d / f"{name}.tar.gz").write_bytes(b"12345")


def test_backup_list_json_is_the_only_stdout(tmp_path, capsys):
    _write_backup(tmp_path, "agra-backup-20261001T010000", backup_host="mon1", backup_include_prometheus_tsdb="true")

    assert main(["backup", "list", "--json", "-d", str(tmp_path)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == [{
        "name": "agra-backup-20261001T010000",
        "date": "",
        "host": "mon1",
        "safety": False,
        "prometheus_tsdb": True,
        "database_included": None,
        "size_bytes": 5,
        "manifest": str(tmp_path / "agra-backup-20261001T010000.yml"),
        "tarball": str(tmp_path / "agra-backup-20261001T010000.tar.gz"),
        "tarball_exists": True,
    }]


def test_backup_list_json_empty_and_missing_dir(tmp_path, capsys):
    assert main(["backup", "list", "--json", "-d", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(["backup", "list", "--json", "-d", str(tmp_path / "nope")]) == 0
    assert json.loads(capsys.readouterr().out) == []


@pytest.mark.parametrize("argv", [
    ["destroy", "--yes"],
    ["destroy", "--yes-i"],
    ["genpwd", "--force", "--yes"],
    ["restore", "-n", "x", "--yes-i-really"],
    ["backup", "create", "--include-prom"],
])
def test_long_options_cannot_be_abbreviated(argv):
    # argparse would read `--yes` as `--yes-i-really-mean-it` (RULES §8).
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(argv)
    assert exc.value.code == 2
