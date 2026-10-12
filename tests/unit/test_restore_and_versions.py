"""Backup name resolution and installed-versions helpers."""
from __future__ import annotations

import pytest

from pathlib import Path

from agra.cli import main
from agra.commands.restore import _resolve_manifest_from_name
from agra.utils.backups import manifest_for, tarball_for
from agra.utils.versions import entry_versions, major_version

@pytest.fixture
def backup_dir(tmp_path):
    for name in ("agra-backup-20261001T010000", "agra-backup-20261002T010000"):
        (tmp_path / f"{name}.yml").write_text(f"backup_name: {name}\n")
        (tmp_path / f"{name}.tar.gz").write_bytes(b"x")
    return tmp_path


def test_resolve_exact_name(backup_dir):
    assert _resolve_manifest_from_name("agra-backup-20261001T010000", backup_dir) == \
        backup_dir / "agra-backup-20261001T010000.yml"


def test_resolve_unknown_name(backup_dir):
    assert _resolve_manifest_from_name("agra-backup-19990101T000000", backup_dir) is None


def test_resolve_does_not_fuzzy_match(backup_dir):
    assert _resolve_manifest_from_name("2026", backup_dir) is None
    assert _resolve_manifest_from_name("agra-backup-20261001", backup_dir) is None


def test_resolve_bare_file_names_in_backup_dir(backup_dir):
    expected = backup_dir / "agra-backup-20261001T010000.yml"
    assert _resolve_manifest_from_name("agra-backup-20261001T010000.yml", backup_dir) == expected
    assert _resolve_manifest_from_name("agra-backup-20261001T010000.tar.gz", backup_dir) == expected


@pytest.mark.parametrize("path,manifest,tarball", [
    ("/b/agra-backup-mon1-20261001T010000.tar.gz", "agra-backup-mon1-20261001T010000.yml", "agra-backup-mon1-20261001T010000.tar.gz"),
    ("/b/agra-backup-mon1.example.com-20261001T010000.yml", "agra-backup-mon1.example.com-20261001T010000.yml",
     "agra-backup-mon1.example.com-20261001T010000.tar.gz"),
])
def test_manifest_and_tarball_names(path, manifest, tarball):
    # Path.with_suffix turned X.tar.gz into X.tar.yml.
    assert manifest_for(Path(path)).name == manifest
    assert tarball_for(Path(path)).name == tarball


@pytest.mark.parametrize("tag,major", [
    ("11.2.0", 11),
    ("v2.53.0", 2),
    ("1.27-alpine", 1),
    ("latest", None),
    ("", None),
])
def test_major_version(tag, major):
    assert major_version(tag) == major


def test_entry_versions_stringifies_and_tolerates_missing():
    data = {"current": {"versions": {"grafana_tag": 11.2, "prometheus_tag": "v2.53.0"}}}

    assert entry_versions(data, "current") == {"grafana_tag": "11.2", "prometheus_tag": "v2.53.0"}
    assert entry_versions(data, "previous") == {}


def _capture_restore(monkeypatch):
    import agra.commands.restore as restore

    calls = []
    monkeypatch.setattr(restore, "run_playbook", lambda name, **kw: calls.append((name, kw)) or 0)
    monkeypatch.setenv("AGRA_NON_INTERACTIVE", "1")
    return calls


def test_restore_sends_the_control_node_copy(backup_dir, monkeypatch, inventory_file):
    calls = _capture_restore(monkeypatch)

    rc = main(["restore", "-i", str(inventory_file), "-n", "agra-backup-20261002T010000", "-d", str(backup_dir),
               "--no-precheck", "--yes-i-really-mean-it"])

    assert rc == 0
    evars = calls[0][1]["extra_vars"]
    assert evars["restore_backup_name"] == "agra-backup-20261002T010000"
    assert evars["restore_local_tarball"] == str(backup_dir / "agra-backup-20261002T010000.tar.gz")
    assert evars["restore_manifest_path"] == str(backup_dir / "agra-backup-20261002T010000.yml")


def test_restore_from_tarball_finds_its_manifest(backup_dir, monkeypatch, inventory_file):
    calls = _capture_restore(monkeypatch)

    rc = main(["restore", "-i", str(inventory_file), "-f", str(backup_dir / "agra-backup-20261001T010000.tar.gz"),
               "--no-precheck", "--yes-i-really-mean-it"])

    assert rc == 0
    assert calls[0][1]["extra_vars"]["restore_manifest_path"] == str(backup_dir / "agra-backup-20261001T010000.yml")


def test_restore_refuses_partial_name(backup_dir, monkeypatch, inventory_file):
    calls = _capture_restore(monkeypatch)

    rc = main(["restore", "-i", str(inventory_file), "-n", "2026", "-d", str(backup_dir),
               "--no-precheck", "--yes-i-really-mean-it"])

    assert rc != 0 and calls == []


def test_backup_list_checks_the_local_tarball(backup_dir, capsys):
    # Manifest points at the master's path; the restorable copy sits next to it.
    (backup_dir / "agra-backup-20261001T010000.yml").write_text(
        "backup_name: agra-backup-20261001T010000\nbackup_tarball_path: /var/lib/agra/backups/x.tar.gz\n")
    (backup_dir / "agra-backup-20261002T010000.tar.gz").unlink()

    assert main(["backup", "list", "-d", str(backup_dir)]) == 0
    rows = {line.split()[2]: line for line in capsys.readouterr().out.splitlines() if "agra-backup-" in line and "│" in line}
    assert "✅" in rows["agra-backup-20261001T010000"]
    assert "❌" in rows["agra-backup-20261002T010000"]
