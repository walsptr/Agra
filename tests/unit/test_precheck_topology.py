"""Topology (PR 15): [grafana] and [prometheus] must be exactly [monitoring].

Runs precheck.yml's validation play for real (localhost only, no become). The
node play gets a host pattern that matches nothing, so no node is contacted."""
from __future__ import annotations

import pytest

from agra.constants import PROJECT_ROOT
from conftest import needs_ansible, run_playbook_locally

pytestmark = needs_ansible

VARS = {
    "_agra_cli_inventory_explicit_confirmed": True,
    "_agra_precheck_limit": "no-such-host-in-this-test",
    "enable_https": False,  # no certificate on the control node
    "grafana_admin_password": "unit-test-password",
    "grafana_secret_key": "unit-test-secret-key-0123456789",
    "keepalived_auth_pass": "unittest",
    "monitoring_vip": "192.0.2.100",
    "grafana_tag": "11.2.0", "prometheus_tag": "v2.53.0", "node_exporter_tag": "v1.8.2",
}

CHILDREN = "[grafana:children]\nmonitoring\n[prometheus:children]\nmonitoring\n"
MONITORING = "[monitoring]\nmon1 ansible_host=192.0.2.11\nmon2 ansible_host=192.0.2.12\n[node_exporter:children]\nmonitoring\n"


def _precheck(tmp_path, inventory: str, **extra):
    return run_playbook_locally(tmp_path, "precheck.yml", inventory, {**VARS, **extra})


def test_children_of_monitoring_pass(tmp_path):
    result = _precheck(tmp_path, MONITORING + CHILDREN)
    assert result.returncode == 0, result.stdout[-2000:]
    assert "AGRA PRECHECK PASSED" in result.stdout


def test_same_hosts_listed_explicitly_pass(tmp_path):
    result = _precheck(tmp_path, MONITORING + "[grafana]\nmon2\nmon1\n[prometheus]\nmon1\nmon2\n")
    assert result.returncode == 0, result.stdout[-2000:]


@pytest.mark.parametrize("groups,broken", [
    ("[grafana]\nmon1\n[prometheus:children]\nmonitoring\n", "grafana"),            # subset
    ("[grafana:children]\nmonitoring\n[prometheus]\ng9 ansible_host=192.0.2.9\n", "prometheus"),  # elsewhere
    ("[prometheus:children]\nmonitoring\n", "grafana"),                             # group missing
])
def test_split_topology_fails_before_touching_nodes(tmp_path, groups, broken):
    result = _precheck(tmp_path, MONITORING + groups)
    assert result.returncode != 0
    assert f"[{broken}] = " in result.stdout and f"[{broken}:children]" in result.stdout


def test_disabled_service_does_not_need_its_group(tmp_path):
    result = _precheck(tmp_path, MONITORING + "[prometheus:children]\nmonitoring\n", enable_grafana=False)
    assert result.returncode == 0, result.stdout[-2000:]


@pytest.mark.parametrize("name", ["all-in-one", "multinode"])
def test_shipped_inventories_pass(tmp_path, name):
    result = _precheck(tmp_path, (PROJECT_ROOT / "inventory" / name).read_text())
    assert result.returncode == 0, result.stdout[-2000:]
