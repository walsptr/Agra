"""Inventory resolution and -i wiring: agra must never target hosts the operator did not name."""
from __future__ import annotations

import pytest

from agra.cli import build_parser, main
from agra.constants import DEFAULT_INVENTORY
from agra.errors import InventoryNotFoundError
from agra.utils.paths import resolve_inventory


@pytest.fixture(autouse=True)
def _no_env_inventory(monkeypatch):
    monkeypatch.delenv("AGRA_INVENTORY", raising=False)


def test_explicit_absolute_inventory(inventory_file):
    assert resolve_inventory(str(inventory_file)) == inventory_file


def test_explicit_missing_inventory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_inventory(str(tmp_path / "nope"))


def test_env_inventory_used_when_no_flag(monkeypatch, inventory_file):
    monkeypatch.setenv("AGRA_INVENTORY", str(inventory_file))

    assert resolve_inventory(None) == inventory_file


def test_flag_beats_env(monkeypatch, inventory_file, tmp_path):
    other = tmp_path / "other.ini"
    other.write_text("[monitoring]\n")
    monkeypatch.setenv("AGRA_INVENTORY", str(other))

    assert resolve_inventory(str(inventory_file)) == inventory_file


def test_default_inventory_when_nothing_set():
    assert resolve_inventory(None) == DEFAULT_INVENTORY


def test_subcommand_inventory_flag_is_parsed():
    args = build_parser().parse_args(["deploy", "-i", "inventory/multinode"])

    assert args.inventory == "inventory/multinode"


def test_env_inventory_typo_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("AGRA_INVENTORY", str(tmp_path / "typo"))

    with pytest.raises(FileNotFoundError):
        resolve_inventory(None)


def test_relative_inventory_resolves_against_cwd(monkeypatch, tmp_path):
    (tmp_path / "site-inv").write_text("[monitoring]\n")
    monkeypatch.chdir(tmp_path)

    assert resolve_inventory("site-inv") == tmp_path / "site-inv"


def test_global_inventory_flag_reaches_command():
    args = build_parser().parse_args(["-i", "inventory/multinode", "deploy"])

    assert args.inventory == "inventory/multinode"


def test_backup_parent_inventory_flag_reaches_create():
    args = build_parser().parse_args(["backup", "-i", "inventory/multinode", "create"])

    assert args.inventory == "inventory/multinode"


@pytest.mark.parametrize("argv", [
    ["backup", "create", "-d", "/srv/agra-backups"],
    ["backup", "-d", "/srv/agra-backups", "create"],
])
def test_backup_dir_flag_reaches_create_at_either_level(argv):
    assert build_parser().parse_args(argv).backup_dir == "/srv/agra-backups"


def test_backup_create_without_dir_flag_keeps_default():
    assert build_parser().parse_args(["backup", "create"]).backup_dir is None


def test_tls_parent_inventory_flag_reaches_regenerate():
    args = build_parser().parse_args(["tls", "-i", "inventory/multinode", "regenerate"])

    assert args.inventory == "inventory/multinode"


def test_env_inventory_relative_resolves_against_cwd(monkeypatch, tmp_path):
    (tmp_path / "site-inv").write_text("[monitoring]\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGRA_INVENTORY", "site-inv")

    assert resolve_inventory(None) == tmp_path / "site-inv"


def test_relative_inventory_missing_in_cwd_points_at_repo_copy(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(InventoryNotFoundError, match="maksudnya .*inventory/multinode"):
        resolve_inventory("inventory/multinode")


def test_subcommand_inventory_beats_global():
    args = build_parser().parse_args(["-i", "global-inv", "deploy", "-i", "cmd-inv"])

    assert args.inventory == "cmd-inv"


@pytest.mark.parametrize("argv", [
    ["deploy"], ["upgrade"], ["rollback"], ["destroy"], ["restore", "-n", "x"],
    ["check"], ["backup"], ["backup", "create"], ["tls"], ["tls", "regenerate"],
])
def test_inventory_defaults_to_none_for_every_command(argv):
    args = build_parser().parse_args(argv)

    assert args.inventory is None


@pytest.mark.parametrize("argv,attr,expected", [
    (["backup", "--no-precheck", "create"], "precheck", False),
    (["backup", "create"], "precheck", True),
    (["backup", "create", "--no-precheck"], "precheck", False),
    (["backup", "-l", "mon1", "create"], "limit", "mon1"),
    (["backup", "-t", "grafana", "create"], "tags", ["grafana"]),
    (["backup", "-v", "create"], "verbose", 1),
    (["backup", "-d", "/srv/bk", "list"], "backup_dir", "/srv/bk"),
    (["tls", "-l", "mon1", "regenerate"], "limit", "mon1"),
    (["tls", "-e", "x=1", "regenerate"], "extra_vars", ["x=1"]),
    (["certificates", "-c", "/srv/my.crt", "info"], "cert_path", "/srv/my.crt"),
    (["certificates", "-k", "/srv/my.key", "generate"], "key_path", "/srv/my.key"),
    (["certificates", "generate"], "cert_path", None),
])
def test_parent_level_options_survive_subcommand(argv, attr, expected):
    assert getattr(build_parser().parse_args(argv), attr) == expected


def test_missing_inventory_is_a_clean_error_not_a_traceback(etc_agra, tmp_path, capsys):
    assert main(["deploy", "-i", str(tmp_path / "nope")]) == 2
    captured = capsys.readouterr()
    assert "tidak ditemukan" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_global_inventory_reaches_the_playbook(etc_agra, inventory_file, monkeypatch):
    import agra.commands.deploy as deploy

    seen = []
    monkeypatch.setattr(deploy, "run_playbook", lambda name, **kw: seen.append(kw["inventory"]) or 0)

    assert main(["-i", str(inventory_file), "deploy"]) == 0
    assert seen == [str(inventory_file)]
