"""destroy (PR 14): purge flags map exactly onto the playbook vars, and every
purge only touches hosts whose group deploys that service — an app server
that is only in [node_exporter] keeps its own /etc/nginx and /etc/keepalived."""
from __future__ import annotations

import pytest
import yaml

from agra.cli import main
from agra.constants import PLAYBOOK_DIR

PLAY = yaml.safe_load((PLAYBOOK_DIR / "destroy.yml").read_text())[0]
PURGE_TASKS = [t for t in PLAY["tasks"] if "PURGE" in t["name"]]


@pytest.mark.parametrize("flags,data,config", [
    ([], False, False),
    (["--purge-data"], True, False),
    (["--purge-config"], False, True),
    (["--purge-all"], True, True),
    (["--purge-data", "--purge-config"], True, True),
])
def test_purge_flags_map_onto_playbook_vars(flags, data, config, monkeypatch, etc_agra, inventory_file):
    import agra.commands.destroy as destroy

    calls = []
    monkeypatch.setattr(destroy, "run_playbook", lambda name, **kw: calls.append((name, kw)) or 0)

    assert main(["destroy", "-i", str(inventory_file), "--yes-i-really-mean-it", *flags]) == 0

    (name, kw), = calls
    assert name == "destroy"
    assert kw["extra_vars"] == {"destroy_confirm": True, "destroy_purge_data": data, "destroy_purge_config": config}


def test_play_covers_every_group_and_asserts_before_connecting():
    assert set(PLAY["hosts"].split(":")) == {"monitoring", "grafana", "prometheus", "node_exporter"}
    assert PLAY["gather_facts"] is False
    assert PLAY["pre_tasks"][0]["ansible.builtin.assert"]["that"] == ["_ds_confirm"]


def test_both_purge_tasks_exist():
    assert len(PURGE_TASKS) == 2


@pytest.mark.parametrize("task", PURGE_TASKS, ids=lambda t: t["name"][:40])
def test_every_purge_is_scoped_to_the_group_that_deploys_it(task):
    when = " ".join(task["when"])
    assert "inventory_hostname in groups[item.group]" in when
    assert all(item.get("group") for item in task["loop"]), task["loop"]


def test_nginx_and_keepalived_config_only_on_monitoring():
    config_task = next(t for t in PURGE_TASKS if "CONFIG" in t["name"])
    groups = {item["path"].split("_config_dir")[0].strip("{ ").removeprefix("_svc_"): item["group"]
              for item in config_task["loop"]}

    assert groups == {"grafana": "grafana", "prometheus": "prometheus", "node_exporter": "node_exporter",
                      "nginx": "monitoring", "keepalived": "monitoring"}
