"""Lifecycle guards (PR 16): no upgrade without a backup, retention can never
delete every backup, restore never skips its safety backup, tags cannot skip
the health gate or the version record, and backup/restore/destroy use the
same Grafana/Prometheus paths as the roles."""
from __future__ import annotations

import pytest
import yaml

from agra.cli import main
from agra.constants import PLAYBOOK_DIR
from conftest import needs_ansible, run_playbook_locally


def _stub(monkeypatch, module, results):
    calls = []

    def fake(name, **kw):
        calls.append((name, kw))
        return results.get(name, 0)

    monkeypatch.setattr(module, "run_playbook", fake)
    return calls


# ── upgrade: backup first, or nothing ──────────────────────────────────────
@pytest.mark.parametrize("backup_rc", [1, 2, 4])
def test_upgrade_aborts_when_the_backup_fails(backup_rc, monkeypatch, etc_agra, inventory_file):
    import agra.commands.upgrade as upgrade

    calls = _stub(monkeypatch, upgrade, {"backup": backup_rc})

    rc = main(["upgrade", "-i", str(inventory_file), "--no-precheck", "--grafana-tag", "11.3.0"])

    assert rc == backup_rc
    assert [name for name, _ in calls] == ["backup"]


def test_upgrade_backs_up_the_current_state_then_upgrades(monkeypatch, etc_agra, inventory_file):
    import agra.commands.upgrade as upgrade

    calls = _stub(monkeypatch, upgrade, {})

    assert main(["upgrade", "-i", str(inventory_file), "--no-precheck", "-l", "mon2", "--grafana-tag", "11.3.0"]) == 0

    (b_name, b_kw), (u_name, u_kw) = calls
    assert (b_name, u_name) == ("backup", "upgrade")
    # The backup is the master at its current version: no -l, no new tag.
    assert b_kw.get("limit") is None and not b_kw.get("extra_vars")
    assert u_kw["limit"] == "mon2" and u_kw["extra_vars"] == {"grafana_tag": "11.3.0"}


@pytest.mark.parametrize("command", [["upgrade", "--grafana-tag", "11.3.0"], ["rollback", "--yes"]])
def test_partial_rollout_says_versions_are_not_recorded(command, monkeypatch, etc_agra, inventory_file, capsys):
    import agra.commands.rollback as rollback
    import agra.commands.upgrade as upgrade

    _stub(monkeypatch, upgrade, {})
    _stub(monkeypatch, rollback, {})
    monkeypatch.setattr(rollback, "load_installed_versions", lambda: {
        "current": {"versions": {"grafana_tag": "11.3.0"}}, "previous": {"versions": {"grafana_tag": "11.2.0"}}})

    argv = [command[0], "-i", str(inventory_file), "--no-precheck", *command[1:]]
    assert main(argv + ["-l", "mon2"]) == 0
    assert "TIDAK dicatat" in capsys.readouterr().err
    assert main(argv) == 0
    assert "TIDAK dicatat" not in capsys.readouterr().err


# ── rollback target ────────────────────────────────────────────────────────
@pytest.mark.parametrize("extra,expected", [
    ([], {"grafana_tag": "11.2.0", "prometheus_tag": "v2.52.0"}),
    (["--service", "grafana"], {"grafana_tag": "11.2.0"}),
    (["--grafana-tag", "11.1.0"], {"grafana_tag": "11.1.0"}),
    (["--service", "prometheus", "--grafana-tag", "11.1.0"], {"grafana_tag": "11.1.0", "prometheus_tag": "v2.52.0"}),
])
def test_rollback_targets_previous_or_the_pin(extra, expected, monkeypatch, etc_agra, inventory_file):
    import agra.commands.rollback as rollback

    calls = _stub(monkeypatch, rollback, {})
    monkeypatch.setattr(rollback, "load_installed_versions", lambda: {
        "current": {"versions": {"grafana_tag": "11.3.0", "prometheus_tag": "v2.53.0", "nginx_tag": "1.27"}},
        "previous": {"versions": {"grafana_tag": "11.2.0", "prometheus_tag": "v2.52.0", "nginx_tag": "1.27"}},
    })

    assert main(["rollback", "-i", str(inventory_file), "--no-precheck", "--yes", *extra]) == 0

    (name, kw), = calls
    # Only what changes is applied; nginx is already at its `previous` tag.
    assert name == "rollback" and kw["extra_vars"] == expected


def test_rollback_without_previous_or_pin_refuses(monkeypatch, etc_agra, inventory_file):
    import agra.commands.rollback as rollback

    calls = _stub(monkeypatch, rollback, {})
    monkeypatch.setattr(rollback, "load_installed_versions", lambda: {})

    assert main(["rollback", "-i", str(inventory_file), "--no-precheck", "--yes"]) == 1
    assert calls == []


# ── backup retention ───────────────────────────────────────────────────────
@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_backup_retention_below_one_is_rejected(value, monkeypatch, etc_agra, inventory_file):
    import agra.commands.backup as backup

    calls = _stub(monkeypatch, backup, {})
    with pytest.raises(SystemExit) as exc:
        main(["backup", "create", "-i", str(inventory_file), "--no-precheck", "-n", value])
    assert exc.value.code == 2 and calls == []


@pytest.mark.parametrize("flags,expected", [(["-n", "1"], {"backup_retention_count": 1}), ([], {})])
def test_backup_retention_is_passed_when_given(flags, expected, monkeypatch, etc_agra, inventory_file):
    import agra.commands.backup as backup

    calls = _stub(monkeypatch, backup, {})
    assert main(["backup", "create", "-i", str(inventory_file), "--no-precheck", *flags]) == 0
    assert (calls[0][1]["extra_vars"] or {}) == expected


PRECHECK_VARS = {
    "_agra_cli_inventory_explicit_confirmed": True, "_agra_precheck_limit": "no-such-host-in-this-test",
    "enable_https": False, "grafana_admin_password": "unit-test-password",
    "grafana_secret_key": "unit-test-secret-key-0123456789",
}
INVENTORY = "[monitoring]\nmon1 ansible_host=192.0.2.11\n[grafana:children]\nmonitoring\n" \
            "[prometheus:children]\nmonitoring\n[node_exporter:children]\nmonitoring\n"


@needs_ansible
@pytest.mark.parametrize("count,ok", [(0, False), (-3, False), (1, True)])
def test_precheck_rejects_retention_below_one(count, ok, tmp_path):
    result = run_playbook_locally(tmp_path, "precheck.yml", INVENTORY, {**PRECHECK_VARS, "backup_retention_count": count})
    assert (result.returncode == 0) is ok, result.stdout[-1500:]
    assert ("membuat setiap backup menghapus semua backup" in result.stdout) is not ok


# ── restore never skips its safety backup ──────────────────────────────────
@needs_ansible
def test_restore_refuses_without_its_safety_backup(tmp_path):
    """--skip-tags backup used to skip the safety backup and still overwrite
    grafana.db. Runs restore.yml for real against this machine with become off,
    Grafana/Prometheus disabled and every path under tmp_path."""
    tarball = tmp_path / "agra-backup-x.tar.gz"
    tarball.write_bytes(b"not a real backup")
    result = run_playbook_locally(
        tmp_path, "restore.yml",
        "[monitoring]\nmon1 ansible_connection=local ansible_become=false\n"
        "[grafana:children]\nmonitoring\n[prometheus:children]\nmonitoring\n",
        {"restore_confirm": True, "restore_backup_name": "agra-backup-x", "restore_local_tarball": str(tarball),
         "enable_grafana": False, "enable_prometheus": False,
         "backup_root_dir": str(tmp_path / "master"), "backup_control_node_dir": str(tmp_path / "ctrl"),
         "grafana_data_dir": str(tmp_path / "g"), "grafana_config_dir": str(tmp_path / "gc"),
         "prometheus_data_dir": str(tmp_path / "p")},
        "--skip-tags", "backup",
    )
    assert result.returncode != 0
    assert "Safety backup sebelum restore tidak berjalan" in result.stdout, result.stdout[-2000:]
    assert not (tmp_path / "master" / "agra-backup-x.tar.gz").exists()


def _plays(name):
    return yaml.safe_load((PLAYBOOK_DIR / name).read_text())


def test_restore_import_of_the_safety_backup_runs_under_restore_tags():
    imp = next(p for p in _plays("restore.yml") if p.get("ansible.builtin.import_playbook") == "backup.yml")
    assert "restore" in imp["tags"]


# ── tags cannot skip the health gate or the version record ─────────────────
def test_health_gate_and_version_record_are_always_tagged():
    tasks = [t for play in _plays("upgrade_monitoring.yml") for t in play.get("post_tasks", []) + play.get("tasks", [])]
    gated = [t for t in tasks if t.get("ansible.builtin.import_tasks") in
             ("tasks/health_gate.yml", "tasks/record_installed_versions.yml")]
    assert len(gated) == 4
    assert all("always" in t.get("tags", []) for t in gated), [t["name"] for t in gated]


# ── one set of service paths, derived like the roles ───────────────────────
@pytest.mark.parametrize("playbook", ["backup.yml", "restore.yml", "destroy.yml"])
def test_lifecycle_playbooks_derive_service_paths_like_the_roles(playbook):
    text = (PLAYBOOK_DIR / playbook).read_text()
    assert "vars/service_paths.yml" in text
    for hardcoded in ("/var/lib/agra/grafana", "/etc/grafana", "/var/lib/agra/prometheus", "/etc/prometheus"):
        assert f"default('{hardcoded}" not in text, f"{playbook} hardcodes {hardcoded}"


def test_service_paths_follow_grafana_data_dir():
    paths = yaml.safe_load((PLAYBOOK_DIR / "vars" / "service_paths.yml").read_text())
    assert "_svc_grafana_data_dir ~ '/grafana.db'" in paths["_svc_grafana_db"]
    assert "_svc_grafana_config_dir ~ '/provisioning'" in paths["_svc_grafana_provisioning_dir"]
