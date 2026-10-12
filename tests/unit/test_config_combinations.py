"""Config combinations (PR 18): non-default ports, paths, addresses and hosts
render into configs that still work. The logic under test is taken from the
repo's own tasks/templates and run through Ansible for real (localhost only)."""
from __future__ import annotations

import json
import re

import pytest
import yaml

from agra.constants import PLAYBOOK_DIR, PROJECT_ROOT
from conftest import needs_ansible, run_playbook_locally

ROLES = PROJECT_ROOT / "ansible" / "roles"
INVENTORY = ("[monitoring]\nmon1 ansible_host=192.0.2.11 ansible_connection=local ansible_become=false\n"
             "[grafana:children]\nmonitoring\n[prometheus:children]\nmonitoring\n[node_exporter:children]\nmonitoring\n")


def _task(path, name_start):
    return next(t for t in yaml.safe_load((ROLES / path).read_text()) if t["name"].startswith(name_start))


def _run(tmp_path, tasks, expose, extra=None, inventory=INVENTORY, vars_files=(), hosts="mon1"):
    """Run `tasks` on `hosts`, then return {name: value} for every expression in `expose`."""
    out = tmp_path / "out.json"
    play = tmp_path / "play.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": hosts, "gather_facts": False, "become": False, "vars_files": [str(f) for f in vars_files],
        "tasks": [*tasks, {"ansible.builtin.copy": {
            "dest": str(out), "content": "{{ " + "{" + ", ".join(f"'{k}': {v}" for k, v in expose.items()) + "} | to_json }}"}}],
    }]))
    result = run_playbook_locally(tmp_path, str(play), inventory, extra or {})
    assert result.returncode == 0, result.stdout[-3000:]
    return json.loads(out.read_text())


# ── one public URL, with the port when it is not the scheme default ─────────
PUBLIC = PLAYBOOK_DIR / "vars" / "public_url.yml"
URLS = {"url": "_agra_public_url | trim", "prom": "_agra_prometheus_public_url | trim",
        "sub": "_agra_prometheus_subpath_url | trim"}


@needs_ansible
@pytest.mark.parametrize("extra,url", [
    ({}, "https://192.0.2.11/"),                                        # never inventory_hostname
    ({"monitoring_vip": "192.0.2.100"}, "https://192.0.2.100/"),
    ({"grafana_domain": "g.example.com", "monitoring_vip": "192.0.2.100"}, "https://g.example.com/"),
    ({"nginx_https_port": 8443}, "https://192.0.2.11:8443/"),
    ({"enable_https": False}, "http://192.0.2.11/"),
    ({"enable_https": False, "nginx_http_port": 8080}, "http://192.0.2.11:8080/"),
    ({"enable_nginx": False}, "http://192.0.2.11:3000/"),
])
def test_public_url(extra, url, tmp_path):
    got = _run(tmp_path, [], URLS, extra, vars_files=[PUBLIC], hosts="localhost")
    assert got["url"] == url
    assert got["prom"] == got["sub"] == ""


@needs_ansible
@pytest.mark.parametrize("extra,prom,sub", [
    ({"expose_prometheus_via_nginx": True, "nginx_https_port": 8443},
     "https://192.0.2.11:8443/prometheus/", "https://192.0.2.11:8443/prometheus/"),
    ({"prometheus_domain": "p.example.com", "expose_prometheus_via_nginx": True},
     "https://p.example.com/", "https://192.0.2.11/prometheus/"),
    ({"prometheus_domain": "p.example.com", "enable_prometheus": False}, "", ""),
])
def test_prometheus_public_url(extra, prom, sub, tmp_path):
    got = _run(tmp_path, [], URLS, extra, vars_files=[PUBLIC], hosts="localhost")
    assert (got["prom"], got["sub"]) == (prom, sub)


def test_every_url_user_reads_the_shared_definition():
    for path in ("roles/grafana/tasks/main.yml", "roles/prometheus/tasks/config.yml", "playbooks/deploy.yml"):
        text = (PROJECT_ROOT / "ansible" / path).read_text()
        assert "_agra_public_url" in text or "_agra_prometheus_subpath_url" in text, path
        assert "inventory_hostname }}/prometheus" not in text and "_gf_host_fallback" not in text, path
    plays = yaml.safe_load((PLAYBOOK_DIR / "deploy.yml").read_text()) \
        + yaml.safe_load((PLAYBOOK_DIR / "upgrade_monitoring.yml").read_text())
    for play in plays:
        roles = {r["role"] for r in play.get("roles", [])}
        if roles & {"grafana", "prometheus"} or play["name"] == "AGRA DEPLOY SUMMARY":
            assert "vars/public_url.yml" in play.get("vars_files", []), play["name"]


# ── Prometheus keeps serving at / with an external URL ─────────────────────
@needs_ansible
@pytest.mark.parametrize("extra,external", [
    ({"prometheus_web_external_url": "https://p.example.com/prom/"}, "https://p.example.com/prom/"),
    ({"expose_prometheus_via_nginx": True, "nginx_https_port": 8443}, "https://192.0.2.11:8443/prometheus/"),
    ({}, None),
])
def test_prometheus_external_url_keeps_routes_at_root(extra, external, tmp_path):
    defaults = ROLES / "prometheus" / "defaults" / "main.yml"
    got = _run(tmp_path, [_task("prometheus/tasks/config.yml", "Prometheus (Config) - Build CLI")],
               {"args": "_prometheus_extra_args | split"}, extra, vars_files=[defaults, PUBLIC])
    args = got["args"]
    if external:
        assert f"--web.external-url={external}" in args and "--web.route-prefix=/" in args
    else:
        assert not [a for a in args if a.startswith(("--web.external-url", "--web.route-prefix"))]


# ── nginx: container paths, redirect port, IPv6, stapling resolver ─────────
NGINX_VARS = [ROLES / "nginx" / "defaults" / "main.yml", ROLES / "nginx" / "vars" / "main.yml"]
NGINX_FACTS = _task("nginx/tasks/config.yml", "Nginx (Config) - IPv6, OCSP stapling")


def _render_nginx(tmp_path, extra):
    out = tmp_path / "rendered"
    out.mkdir()
    tasks = [NGINX_FACTS] + [
        {"ansible.builtin.template": {"src": str(ROLES / "nginx" / "templates" / src), "dest": str(out / src.replace("/", "_"))}}
        for src in ("nginx.conf.j2", "sites-available/grafana.conf.j2", "sites-available/prometheus.conf.j2")]
    got = _run(tmp_path, tasks, {"resolvers": "_nginx_resolvers", "stapling": "_nginx_stapling"},
               {"prometheus_domain": "p.example.com", "ansible_facts": {"dns": {"nameservers": ["127.0.0.53", "fd00::1"]},
                                                                         "all_ipv6_addresses": ["fe80::1"]},
                **extra}, vars_files=NGINX_VARS)
    return got, "\n".join(p.read_text() for p in sorted(out.iterdir()))


@needs_ansible
def test_nginx_configs_use_container_paths_whatever_the_host_dirs(tmp_path):
    _, text = _render_nginx(tmp_path, {"nginx_config_dir": "/opt/agra-host/nginx", "nginx_log_dir": "/opt/agra-host/log",
                                       "nginx_cache_dir": "/opt/agra-host/cache"})
    assert "/opt/agra-host" not in text
    assert "include /etc/nginx/mime.types;" in text and "ssl_certificate     /etc/nginx/ssl/agra.crt;" in text


def test_site_links_are_relative():
    tasks = yaml.safe_load((ROLES / "nginx/tasks/config.yml").read_text())
    links = [t["ansible.builtin.file"] for t in tasks if t.get("ansible.builtin.file", {}).get("state") == "link"]
    assert len(links) == 2 and all(link["src"].startswith("../sites-available/") for link in links)


@needs_ansible
@pytest.mark.parametrize("port,location", [(443, "https://$host$request_uri"), (8443, "https://$host:8443$request_uri")])
def test_http_redirect_keeps_the_https_port(port, location, tmp_path):
    _, text = _render_nginx(tmp_path, {"nginx_https_port": port})
    assert text.count(f"return 301 {location};") == 2  # Grafana site + prometheus_domain site


@needs_ansible
@pytest.mark.parametrize("ipv6", [True, False])
def test_ipv6_listen_follows_the_host(ipv6, tmp_path):
    got, text = _render_nginx(tmp_path, {"ansible_facts": {"dns": {"nameservers": ["127.0.0.53", "fd00::1"]},
                                                          "all_ipv6_addresses": ["fe80::1"] if ipv6 else []},
                                         "enable_ssl_stapling": True})
    assert ("listen [::]:" in text) is ipv6
    assert got["resolvers"] == (["127.0.0.53", "[fd00::1]"] if ipv6 else ["127.0.0.53"])
    assert ("ipv6=off" in text) is not ipv6


@needs_ansible
@pytest.mark.parametrize("extra,resolver", [
    ({"enable_ssl_stapling": True}, "resolver 127.0.0.53 [fd00::1] valid=300s;"),
    ({"enable_ssl_stapling": True, "nginx_resolver": "1.1.1.1 9.9.9.9"}, "resolver 1.1.1.1 9.9.9.9 valid=300s;"),
    ({}, None),                                         # no CA chain copied: stapling off, no resolver
    ({"enable_ssl_stapling": True, "enable_https": False}, None),
])
def test_stapling_always_comes_with_a_resolver(extra, resolver, tmp_path):
    got, text = _render_nginx(tmp_path, extra)
    assert ("ssl_stapling on;" in text) is (resolver is not None) is got["stapling"]
    if resolver:
        assert resolver in text


@needs_ansible
def test_stapling_without_any_nameserver_stops_the_deploy(tmp_path):
    assert_task = _task("nginx/tasks/config.yml", "Nginx (Config) - OCSP stapling butuh resolver")
    play = tmp_path / "play.yml"
    play.write_text(yaml.safe_dump([{"hosts": "mon1", "gather_facts": False, "become": False,
                                     "vars_files": [str(f) for f in NGINX_VARS],
                                     "tasks": [NGINX_FACTS, assert_task]}]))
    result = run_playbook_locally(tmp_path, str(play), INVENTORY, {
        "enable_ssl_stapling": True, "ansible_facts": {"dns": {"nameservers": []}, "all_ipv6_addresses": []}})
    assert result.returncode != 0 and "nginx_resolver" in result.stdout


# ── Grafana reads its dashboards at the container path ─────────────────────
def test_dashboard_provider_points_inside_the_container():
    text = (ROLES / "grafana/templates/provisioning/dashboards/all.yml.j2").read_text()
    assert "path: {{ grafana_container_provisioning_dir }}/dashboards" in text


# ── node_exporter firewall allows every address a scrape can come from ─────
@needs_ansible
def test_scrapers_are_allowed_from_both_addresses(tmp_path):
    inventory = ("[monitoring]\nmon1 ansible_host=192.0.2.11 keepalived_unicast_ip=10.0.0.11\n"
                 "mon2 ansible_host=prom2.example.com keepalived_unicast_ip=10.0.0.12\n"
                 "[prometheus:children]\nmonitoring\n"
                 "[node_exporter]\napp1 ansible_host=192.0.2.50 ansible_connection=local ansible_become=false\n")
    got = _run(tmp_path, [_task("common/tasks/config.yml", "Common - Prometheus nodes that scrape")],
               {"scrapers": "_common_scrapers"}, inventory=inventory, hosts="app1")
    assert got["scrapers"] == [{"host": "mon1", "addrs": ["10.0.0.11", "192.0.2.11"]},
                               {"host": "mon2", "addrs": ["10.0.0.12"]}]


# ── no dead handlers, no floating image tags ───────────────────────────────
def _notified():
    names = set()
    for path in (PROJECT_ROOT / "ansible").rglob("*.yml"):
        for match in re.finditer(r"notify:\s*(\[[^\]]*\]|\n(?:\s+- .+\n)+)", path.read_text()):
            names |= set(re.findall(r"[\w][\w .-]*[\w]", match.group(1)))
    return names


@pytest.mark.parametrize("handlers", sorted(ROLES.glob("*/handlers/main.yml")), ids=lambda p: p.parts[-3])
def test_every_handler_is_notified(handlers):
    notified = _notified()
    for handler in yaml.safe_load(handlers.read_text()):
        assert handler.get("listen", handler["name"]) in notified, f"{handlers}: dead handler {handler['name']}"


@pytest.mark.parametrize("defaults", sorted(ROLES.glob("*/defaults/main.yml")), ids=lambda p: p.parts[-3])
def test_image_tags_are_exact_versions(defaults):
    for key, value in (yaml.safe_load(defaults.read_text()) or {}).items():
        if key.endswith("_tag"):
            assert re.fullmatch(r"v?\d+\.\d+\.\d+(-[a-z0-9]+)?", str(value)), f"{key}: {value} floats"
