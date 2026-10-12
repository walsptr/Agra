"""build_ansible_command is the ONLY place globals/passwords reach Ansible (RULES §15.1)."""
from __future__ import annotations

import json
import os

import pytest

from agra.constants import PLAYBOOKS
from agra.utils.run_playbook import build_ansible_command


def test_injects_globals_then_passwords_as_extra_vars(etc_agra, inventory_file):
    argv, inv = build_ansible_command("deploy", inventory=str(inventory_file))

    assert argv[:2] == ["ansible-playbook", str(PLAYBOOKS["deploy"])]
    assert inv == inventory_file
    globals_arg = f"@{etc_agra / 'globals.yml'}"
    passwords_arg = f"@{etc_agra / 'passwords.yml'}"
    # passwords.yml must come after globals.yml so a secret misplaced in globals loses.
    assert argv.index(globals_arg) < argv.index(passwords_arg)
    assert argv[argv.index(globals_arg) - 1] == "-e"
    assert argv[argv.index(passwords_arg) - 1] == "-e"


def test_genpwd_does_not_inject_etc_vars(etc_agra, inventory_file):
    (etc_agra / "passwords.yml").unlink()  # genpwd is what creates it

    argv, _ = build_ansible_command("genpwd", inventory=str(inventory_file), load_etc_vars=False)

    assert not any(a.startswith("@") for a in argv)


def test_cli_extra_vars_are_json_and_after_etc_files(etc_agra, inventory_file):
    argv, _ = build_ansible_command(
        "precheck", inventory=str(inventory_file),
        extra_vars={"_agra_cli_inventory_explicit_confirmed": True},
    )

    i = argv.index("--extra-vars")
    assert json.loads(argv[i + 1]) == {"_agra_cli_inventory_explicit_confirmed": True}
    assert i > argv.index(f"@{etc_agra / 'passwords.yml'}")


def test_no_secret_values_on_command_line(etc_agra, inventory_file):
    argv, _ = build_ansible_command("deploy", inventory=str(inventory_file))

    assert "unit-test-password" not in " ".join(argv)


def test_tags_limit_verbosity(etc_agra, inventory_file):
    argv, _ = build_ansible_command(
        "deploy", inventory=str(inventory_file), tags=["grafana", "nginx"],
        skip_tags=["common"], limit="mon1", verbosity=7,
    )

    assert argv[argv.index("--tags") + 1] == "grafana,nginx"
    assert argv[argv.index("--skip-tags") + 1] == "common"
    assert argv[argv.index("--limit") + 1] == "mon1"
    assert "-vvvv" in argv  # capped at 4


@pytest.mark.parametrize("missing", ["globals.yml", "passwords.yml"])
def test_missing_etc_file_exits_2(etc_agra, inventory_file, missing):
    (etc_agra / missing).unlink()

    with pytest.raises(SystemExit) as exc:
        build_ansible_command("deploy", inventory=str(inventory_file))
    assert exc.value.code == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_unreadable_passwords_exits_2(etc_agra, inventory_file):
    (etc_agra / "passwords.yml").chmod(0o000)

    with pytest.raises(SystemExit) as exc:
        build_ansible_command("deploy", inventory=str(inventory_file))
    assert exc.value.code == 2


@pytest.mark.parametrize("name", sorted(PLAYBOOKS))
def test_every_registered_playbook_exists(name):
    assert PLAYBOOKS[name].is_file()
