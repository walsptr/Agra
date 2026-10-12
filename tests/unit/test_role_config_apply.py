"""Roles apply what they render, and safely (PR 17): nginx.conf changes reach
the container, every nginx change is validated before reload, cert/key pairs
are checked before copying, the Grafana admin password never reaches argv, and
the keepalived health check fits inside its vrrp_script timeout."""
from __future__ import annotations

import http.server
import shutil
import subprocess
import threading
import time

import pytest
import yaml

from agra.constants import PROJECT_ROOT
from conftest import needs_ansible, run_playbook_locally

ROLES = PROJECT_ROOT / "ansible" / "roles"


def _yaml(path):
    return yaml.safe_load((ROLES / path).read_text())


NGINX_TASKS = _yaml("nginx/tasks/config.yml") + [
    t for block in _yaml("nginx/tasks/ssl.yml") for t in block.get("block", [block])]
NGINX_HANDLERS = _yaml("nginx/handlers/main.yml")


# ── nginx: what is rendered is what runs ───────────────────────────────────
def test_nginx_conf_change_restarts_after_the_syntax_check():
    task = next(t for t in NGINX_TASKS if "Render nginx.conf" in t["name"])
    # Single-file mount: a reload keeps reading the replaced inode.
    assert task["notify"] == ["nginx syntax check", "restart nginx"]


def test_every_nginx_change_is_syntax_checked_first():
    notifying = [t for t in NGINX_TASKS if t.get("notify")]
    assert len(notifying) >= 8
    for task in notifying:
        assert task["notify"][0] == "nginx syntax check", task["name"]


def test_syntax_check_handlers_run_before_reload_and_restart():
    order = [h["name"] for h in NGINX_HANDLERS]
    check = [i for i, h in enumerate(NGINX_HANDLERS) if h.get("listen") == "nginx syntax check"]
    apply = [order.index(n) for n in ("restart nginx docker", "reload nginx docker")]
    assert check and max(check) < min(apply)


def test_syntax_check_reads_the_host_files_with_the_container_mounts():
    handler = next(h for h in NGINX_HANDLERS if h["name"] == "nginx syntax check")
    argv = handler["ansible.builtin.command"]["argv"]
    assert "docker', 'run', '--rm'" in argv and "_nginx_volumes" in argv and "'-t'" in argv
    container = (ROLES / "nginx/tasks/docker.yml").read_text()
    assert "_nginx_volumes" in container and "--volume={{" not in container


def test_container_reading_an_old_nginx_conf_is_restarted():
    tasks = _yaml("nginx/tasks/docker.yml")
    live = next(t for t in tasks if "sha256sum" in str(t.get("ansible.builtin.command", "")))
    assert live["notify"] == ["nginx syntax check", "restart nginx"]
    assert "!=" in live["changed_when"]
    assert tasks[-1].get("ansible.builtin.meta") == "flush_handlers"


# ── nginx: cert/key pairs ──────────────────────────────────────────────────
def _openssl(*args):
    subprocess.run(["openssl", *args], check=True, capture_output=True)


@pytest.fixture
def certs(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl not installed")
    d = tmp_path / "ssl"
    d.mkdir()
    for name in ("a", "b"):
        _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", f"/CN={name}",
                 "-keyout", str(d / f"{name}.key"), "-out", str(d / f"{name}.crt"))
    return d


def _run_ssl(tmp_path, extra):
    play = tmp_path / "ssl.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "all", "gather_facts": False, "become": False,
        "tasks": [{"ansible.builtin.include_role": {"name": str(ROLES / "nginx"), "tasks_from": "ssl"}}],
    }]))
    (tmp_path / "nginx" / "ssl").mkdir(parents=True)
    return run_playbook_locally(
        tmp_path, str(play), "[monitoring]\nmon1 ansible_connection=local ansible_become=false\n",
        {"nginx_config_dir": str(tmp_path / "nginx"), "tls_ca_path": "", "tls_dhparam_path": "", **extra},
        "--check",
    )


@needs_ansible
@pytest.mark.parametrize("pair,ok", [
    ({"tls_cert_path": "a.crt", "tls_key_path": "a.key"}, True),
    ({"tls_cert_path": "a.crt", "tls_key_path": "b.key"}, False),
    ({"tls_cert_path": "a.crt", "tls_key_path": "a.key", "tls_grafana_cert_path": "b.crt"}, False),
    ({"tls_cert_path": "a.crt", "tls_key_path": "a.key",
      "tls_grafana_cert_path": "b.crt", "tls_grafana_key_path": "b.key"}, True),
])
def test_cert_and_key_must_be_a_pair(pair, ok, certs, tmp_path):
    result = _run_ssl(tmp_path, {k: str(certs / v) for k, v in pair.items()})
    assert (result.returncode == 0) is ok, result.stdout[-2000:]
    assert ("bukan private key untuk" in result.stdout) is not ok
    # Nothing is copied when a pair is wrong (the copy task never starts).
    assert ("Copy ke" in result.stdout) is ok


# ── grafana ────────────────────────────────────────────────────────────────
def test_admin_password_reset_never_puts_the_password_in_argv():
    task = next(t for t in _yaml("grafana/tasks/docker.yml") if "reset-admin-password" in str(t))
    argv = task["ansible.builtin.command"]["argv"]
    assert not any("password }}" in a for a in argv), argv
    assert "--password-from-stdin" in argv and "--interactive" in argv
    assert task["ansible.builtin.command"]["stdin"] == "{{ _gf_safe_admin_password }}"
    assert task["no_log"] is True


def test_session_cookie_is_secure_behind_https():
    ini = (ROLES / "grafana/templates/grafana.ini.j2").read_text()
    assert "cookie_secure = {{ grafana_cookie_secure | bool | lower }}" in ini
    default = _yaml("grafana/defaults/main.yml")["grafana_cookie_secure"]
    assert "enable_nginx" in default and "enable_https" in default


# ── keepalived: the check fits inside the vrrp_script timeout ──────────────
class _Slow(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        time.sleep(float(self.path.strip("/").split("/")[0]))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def slow_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _render_healthcheck(tmp_path, urls):
    out = tmp_path / "check.sh"
    play = tmp_path / "render.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "mon1", "gather_facts": False, "become": False,
        "tasks": [{"ansible.builtin.template": {
            "src": str(ROLES / "keepalived/templates/agra_monitoring_healthcheck.sh.j2"),
            "dest": str(out), "mode": "0755"}}],
    }]))
    result = run_playbook_locally(
        tmp_path, str(play),
        "[monitoring]\nmon1 ansible_connection=local ansible_become=false\n"
        "[grafana:children]\nmonitoring\n[prometheus:children]\nmonitoring\n",
        {"keepalived_check_interval": 2, "keepalived_log_file": str(tmp_path / "ka.log"),
         "grafana_health_url": urls[0], "prometheus_health_url": urls[1], "nginx_health_url": urls[2]},
    )
    assert result.returncode == 0, result.stdout[-2000:]
    return out


@needs_ansible
@pytest.mark.parametrize("delays,healthy", [((1.4, 1.4, 1.4), True), ((0, 9, 0), False)])
def test_healthcheck_finishes_inside_the_vrrp_script_timeout(delays, healthy, slow_server, tmp_path):
    if not shutil.which("curl"):
        pytest.skip("curl not installed")
    script = _render_healthcheck(tmp_path, [f"{slow_server}/{d}/x" for d in delays])

    start = time.monotonic()
    rc = subprocess.run(["bash", str(script)], check=False, timeout=30).returncode
    elapsed = time.monotonic() - start

    # keepalived.conf: timeout = interval + 1 = 3s. Past it, the node counts as down.
    assert elapsed < 3, f"took {elapsed:.1f}s"
    assert (rc == 0) is healthy
    if not healthy:
        assert "FAIL prometheus" in (tmp_path / "ka.log").read_text()
