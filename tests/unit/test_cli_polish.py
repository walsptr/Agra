"""CLI loose ends. PR 9: -e cannot override confirmed values, backup list --json,
tls regenerate --days, no dead destroy flags. PR 21: tls regenerate validates
before rotating, certificates info names the right fix, safe cert subjects,
backup list without tracebacks, genpwd leaves third-party credentials alone,
deploy warns about version drift, install.sh under sh."""
from __future__ import annotations

import json
import re
import subprocess

import pytest
import yaml

from agra.cli import build_parser, main
from agra.constants import PROJECT_ROOT
from agra.utils.run_playbook import build_ansible_command
from conftest import needs_ansible, run_playbook_locally


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


def test_tls_regenerate_passes_days_and_cn(monkeypatch, etc_agra, inventory_file):
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


# ── PR 21 ────────────────────────────────────────────────────────────────


def _stub_regenerate(monkeypatch, deploy_rc=0):
    import agra.commands.tls as tls

    calls = []
    monkeypatch.setattr(tls.certificates, "_detect_custom", lambda g, c, k: (False, ""))
    monkeypatch.setattr(tls.certificates, "cmd_generate", lambda a: calls.append("generate") or 0)
    monkeypatch.setattr(tls, "run_playbook", lambda name, **kw: calls.append(name) or deploy_rc)
    return calls


def test_tls_regenerate_validates_the_inventory_before_rotating(monkeypatch, etc_agra, tmp_path, capsys):
    calls = _stub_regenerate(monkeypatch)

    assert main(["tls", "-i", str(tmp_path / "typo"), "regenerate", "-y"]) == 2
    assert calls == []  # the old cert is still in place
    assert "tidak ditemukan" in capsys.readouterr().err


def test_tls_regenerate_validates_extra_vars_and_etc_before_rotating(monkeypatch, etc_agra, inventory_file):
    calls = _stub_regenerate(monkeypatch)
    (etc_agra / "passwords.yml").unlink()

    with pytest.raises(SystemExit) as exc:
        main(["tls", "-i", str(inventory_file), "regenerate", "-y"])
    assert exc.value.code == 2
    assert calls == []


def test_tls_regenerate_failed_distribution_says_how_to_resume(monkeypatch, etc_agra, inventory_file, capsys):
    calls = _stub_regenerate(monkeypatch, deploy_rc=4)

    assert main(["tls", "-i", str(inventory_file), "regenerate", "-y"]) == 4
    assert calls == ["generate", "deploy"]
    assert "--tags nginx" in capsys.readouterr().err


@pytest.fixture
def ssl_dir(tmp_path, monkeypatch):
    """certificates.* pointed at a fake /etc/agra (globals + ssl/)."""
    import agra.commands.certificates as certificates

    ssl = tmp_path / "ssl"
    ssl.mkdir()
    globals_file = tmp_path / "globals.yml"
    globals_file.write_text("{}\n")
    monkeypatch.setattr(certificates, "DEFAULT_CERT", str(ssl / "agra.crt"))
    monkeypatch.setattr(certificates, "DEFAULT_KEY", str(ssl / "agra.key"))
    monkeypatch.setattr(certificates, "GLOBALS_FILE", globals_file)
    monkeypatch.setattr(certificates, "load_globals_file", lambda: yaml.safe_load(globals_file.read_text()) or {})
    return ssl


def _cert(path, days, subj="/CN=mon.example"):
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"{path}.key",
                    "-out", str(path), "-days", str(days), "-subj", subj],
                   check=True, capture_output=True)
    return path


def test_certificates_info_default_cert_is_not_called_custom(ssl_dir, capsys):
    _cert(ssl_dir / "agra.crt", 3)

    assert main(["certificates", "info"]) == 2
    err = capsys.readouterr().err
    assert "CUSTOM" not in err
    assert "agra tls regenerate" in err


def test_certificates_info_custom_cert_in_use_says_deploy(ssl_dir, tmp_path, capsys):
    custom = _cert(tmp_path / "ca-signed.crt", 3)
    (ssl_dir.parent / "globals.yml").write_text(f"tls_cert_path: {custom}\ntls_key_path: {custom}.key\n")

    assert main(["certificates", "info"]) == 2
    err = capsys.readouterr().err
    assert "CUSTOM" in err and "--tags nginx" in err
    assert "agra tls regenerate" not in err and "generate --force" not in err


def test_certificates_info_dash_c_on_a_cert_nginx_does_not_use(ssl_dir, tmp_path, capsys):
    _cert(ssl_dir / "agra.crt", 365)
    other = _cert(tmp_path / "other.crt", 3)

    assert main(["certificates", "info", "-c", str(other)]) == 2
    err = capsys.readouterr().err
    assert "tidak dipakai nginx" in err
    assert "agra tls regenerate" not in err and "agra deploy" not in err


def _subject_and_san(cert):
    out = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-subject", "-nameopt", "RFC2253",
                          "-ext", "subjectAltName"], check=True, capture_output=True, text=True).stdout
    return out


def test_certificates_generate_escapes_the_subject(ssl_dir, capsys):
    (ssl_dir.parent / "globals.yml").write_text("tls_self_signed_organization: 'R&D/Ops+Infra'\n")

    assert main(["certificates", "generate", "--cn", "grafana/a+b"]) == 0
    out = _subject_and_san(ssl_dir / "agra.crt")
    assert "CN=grafana/a\\+b" in out
    assert "O=R&D/Ops\\+Infra" in out
    # Not a hostname: kept out of SAN instead of becoming DNS:grafana/a+b.
    assert "grafana" not in out.split("Subject Alternative Name")[1]
    assert "bukan hostname" in capsys.readouterr().err


@pytest.mark.parametrize("cn, entry", [
    ("10.0.0.5", "IP Address:10.0.0.5"),
    ("mon.example.com", "DNS:mon.example.com"),
])
def test_certificates_generate_san_type_follows_the_cn(cn, entry, ssl_dir):
    assert main(["certificates", "generate", "--cn", cn]) == 0
    san = _subject_and_san(ssl_dir / "agra.crt").split("Subject Alternative Name")[1]
    assert entry in san
    assert f"DNS:{cn}" not in san or entry.startswith("DNS")


def test_certificates_generate_rejects_san_injection(ssl_dir):
    assert main(["certificates", "generate", "--cn", "a.example,DNS:evil.example"]) == 0
    assert "evil" not in _subject_and_san(ssl_dir / "agra.crt").split("Subject Alternative Name")[1]


def test_backup_list_on_a_file_is_an_error_not_a_traceback(tmp_path, capsys):
    f = tmp_path / "not-a-dir"
    f.write_text("")

    assert main(["backup", "list", "-d", str(f)]) == 2
    assert "bukan direktori" in capsys.readouterr().err


def test_backup_list_unreadable_dir_is_an_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    import agra.commands.backup as backup

    def _denied(bdir):
        raise PermissionError(13, "Permission denied", str(bdir))

    monkeypatch.setattr(backup, "_list_entries", _denied)

    assert main(["backup", "list", "--json", "-d", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "chown" in captured.err


@needs_ansible
def test_genpwd_leaves_the_database_password_to_the_operator(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    inventory = "localhost ansible_connection=local ansible_become=false\n"

    first = run_playbook_locally(tmp_path, "genpwd.yml", inventory, {"agra_etc_dir": str(etc)})
    assert first.returncode == 0, first.stdout
    pw = yaml.safe_load((etc / "passwords.yml").read_text())
    assert pw["grafana_database_password"] == ""
    assert len(pw["grafana_admin_password"]) == 16
    assert "grafana_database_password: KOSONG" in first.stdout

    # What the DBA issued survives even --force.
    pw["grafana_database_password"] = "issued-by-dba"
    (etc / "passwords.yml").write_text(yaml.safe_dump(pw))
    forced = run_playbook_locally(tmp_path, "genpwd.yml", inventory,
                                  {"agra_etc_dir": str(etc), "genpwd_force": True, "genpwd_confirm": True})
    assert forced.returncode == 0, forced.stdout
    assert yaml.safe_load((etc / "passwords.yml").read_text())["grafana_database_password"] == "issued-by-dba"


def _stub_deploy(monkeypatch, recorded, globals_tags):
    import agra.commands.deploy as deploy
    import agra.utils.versions as versions

    monkeypatch.setattr(versions, "load_installed_versions", lambda: recorded)
    monkeypatch.setattr(versions, "load_globals_file", lambda: dict(globals_tags))
    monkeypatch.setattr(deploy, "run_playbook", lambda name, **kw: 0)


@pytest.mark.parametrize("globals_tags, extra, drift", [
    ({"grafana_tag": "11.3.0"}, [], "grafana_tag: 11.2.0 → 11.3.0"),
    ({"grafana_tag": "11.2.0"}, ["-e", "grafana_tag=12.0.0"], "grafana_tag: 11.2.0 → 12.0.0"),
    ({"grafana_tag": "11.2.0"}, ["-e", '{"prometheus_tag": "v3.0.0"}'], "prometheus_tag: v2.53.0 → v3.0.0"),
])
def test_deploy_warns_when_versions_drift(globals_tags, extra, drift, monkeypatch, inventory_file, capsys):
    _stub_deploy(monkeypatch, {"current": {"versions": {"grafana_tag": "11.2.0", "prometheus_tag": "v2.53.0"}}},
                 globals_tags)

    assert main(["deploy", "-i", str(inventory_file), *extra]) == 0
    err = capsys.readouterr().err
    assert drift in err
    assert "agra upgrade" in err


@pytest.mark.parametrize("recorded", [
    {},  # first deploy
    {"current": {"versions": {"grafana_tag": "11.2.0"}}},
])
def test_deploy_is_quiet_without_drift(recorded, monkeypatch, inventory_file, capsys):
    _stub_deploy(monkeypatch, recorded, {"grafana_tag": "11.2.0", "nginx_tag": "1.27.5-alpine"})

    assert main(["deploy", "-i", str(inventory_file)]) == 0
    assert "BERBEDA" not in capsys.readouterr().err


def test_install_sh_runs_itself_with_bash():
    # `sh install.sh` on Debian/Ubuntu is dash, which stops at `set -o pipefail`.
    text = (PROJECT_ROOT / "install.sh").read_text()
    assert text.index('exec bash "$0" "$@"') < text.index("set -euo pipefail")


def test_install_sh_looks_for_every_supported_python():
    searched = re.search(r"for py in (.*); do", (PROJECT_ROOT / "install.sh").read_text()).group(1).split()
    classifiers = re.findall(r"Python :: (3\.\d+)", (PROJECT_ROOT / "pyproject.toml").read_text())

    assert classifiers
    assert [f"python{v}" for v in sorted(classifiers, key=lambda v: -int(v.split(".")[1]))] == \
        [py for py in searched if py.startswith("python3.")]
