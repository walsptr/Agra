"""Feature flags (PR 19): a stack without Grafana deploys without Grafana's
secrets. Runs deploy.yml for real with a tag nothing carries, so only its
`always` guard play runs; the node is this machine over a local connection
(facts only, read-only)."""
from __future__ import annotations

import pytest

from conftest import needs_ansible, run_playbook_locally

INVENTORY = "[monitoring]\nmon1 ansible_connection=local ansible_become=false\n[grafana:children]\nmonitoring\n" \
            "[prometheus:children]\nmonitoring\n[node_exporter:children]\nmonitoring\n"


@needs_ansible
@pytest.mark.parametrize("enable_grafana,ok", [(False, True), (True, False)])
def test_deploy_needs_grafana_secrets_only_with_grafana(enable_grafana, ok, tmp_path):
    result = run_playbook_locally(tmp_path, "deploy.yml", INVENTORY, {"enable_grafana": enable_grafana},
                                  "--tags", "agra-unit-test-no-such-tag")
    assert (result.returncode == 0) is ok, result.stdout[-2000:]
    assert ("Secret Grafana" in result.stdout) is not ok
