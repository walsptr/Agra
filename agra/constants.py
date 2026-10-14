"""Konstanta path global untuk CLI."""
from __future__ import annotations
import sysconfig
from pathlib import Path


def _find_data_root() -> Path:
    """Direktori yang berisi ansible/, ansible.cfg, inventory/ dan etc/agra/.

    Checkout repo / `pip install -e .`: induk package `agra/`. Install biasa
    (`pip install .` / wheel): `<prefix>/share/agra` dari data_files setup.py —
    pola kolla-ansible (`share/kolla-ansible`). Prefix venv/sistem dulu, lalu
    skema `--user`.
    """
    candidates = [Path(__file__).resolve().parent.parent]
    # get_preferred_scheme baru ada di Python 3.10.
    user_scheme = sysconfig.get_preferred_scheme("user") if hasattr(sysconfig, "get_preferred_scheme") else "posix_user"
    for kwargs in ({}, {"scheme": user_scheme}):
        try:
            candidates.append(Path(sysconfig.get_path("data", **kwargs)) / "share" / "agra")
        except KeyError:
            continue
    for c in candidates:
        if (c / "ansible" / "playbooks").is_dir():
            return c
    return candidates[0]


PROJECT_ROOT: Path = _find_data_root()

ANSIBLE_DIR: Path = PROJECT_ROOT / "ansible"
PLAYBOOK_DIR: Path = ANSIBLE_DIR / "playbooks"
ROLES_DIR: Path = ANSIBLE_DIR / "roles"

ETC_DIR: Path = Path("/etc/agra")
AGRA_SSL_DIR: Path = ETC_DIR / "ssl"
GLOBALS_FILE: Path = ETC_DIR / "globals.yml"
PASSWORDS_FILE: Path = ETC_DIR / "passwords.yml"
CONFIG_DIR: Path = ETC_DIR / "config"
# Dicatat oleh tasks/record_installed_versions.yml (deploy/upgrade/rollback).
INSTALLED_VERSIONS_FILE: Path = ETC_DIR / ".installed_versions.yml"

INVENTORY_DIR: Path = PROJECT_ROOT / "inventory"
DEFAULT_INVENTORY: Path = INVENTORY_DIR / "all-in-one"
MULTINODE_INVENTORY: Path = INVENTORY_DIR / "multinode"

# Backup di master (backup_root_dir) dan salinannya di control node
# (backup_control_node_dir) — yang dibaca `agra backup list` / `agra restore`.
BACKUP_ROOT_DIR: Path = Path("/var/lib/agra/backups")
CONTROL_BACKUP_DIR: Path = ETC_DIR / "backups"

PLAYBOOKS = {
    "precheck": PLAYBOOK_DIR / "precheck.yml",
    "deploy": PLAYBOOK_DIR / "deploy.yml",
    "upgrade": PLAYBOOK_DIR / "upgrade_monitoring.yml",
    "rollback": PLAYBOOK_DIR / "rollback.yml",
    "destroy": PLAYBOOK_DIR / "destroy.yml",
    "backup": PLAYBOOK_DIR / "backup.yml",
    "restore": PLAYBOOK_DIR / "restore.yml",
    "genpwd": PLAYBOOK_DIR / "genpwd.yml",
}

REQUIRED_COMMANDS = ["ansible-playbook", "ansible"]

# Secret yang HANYA boleh ada di passwords.yml (SCHEMA.md §8).
SECRET_KEYS = (
    "grafana_admin_password",
    "grafana_database_password",
    "grafana_secret_key",
    "keepalived_auth_pass",
    "backup_s3_access_key",
    "backup_s3_secret_key",
)

# Var yang nilainya per-host — dilarang di globals.yml karena extra-vars
# menimpa nilai untuk SEMUA host (RULES.md §14.6).
PER_HOST_KEYS = (
    "monitoring_vip_interface",
    "keepalived_unicast_ip",
)

# Var yang sudah dihapus: masih ada di globals.yml lama tapi tidak berefek.
REMOVED_KEYS = {
    "grafana_nginx_port": "Grafana kini dilayani nginx di nginx_https_port/nginx_http_port (443/80), dengan atau tanpa grafana_domain.",
    "prometheus_nginx_port": "Prometheus tidak lagi dipublikasikan di port sendiri; buka lewat prometheus_domain atau expose_prometheus_via_nginx.",
    # PR 10: var yang tidak pernah dibaca task/template mana pun.
    "tls_self_signed_cn": "CN cert self-signed: `agra certificates generate --cn X` (default grafana_domain > monitoring_vip > hostname).",
    "tls_self_signed_generate": "Cert dibuat di control node dengan `agra certificates generate`.",
    "tls_dhparam_bits": "dhparam selalu 2048-bit (`agra certificates generate --include-dhparam`).",
    "tls_grafana_ca_path": "Gabungkan CA chain ke tls_grafana_cert_path (fullchain).",
    "tls_prometheus_ca_path": "Gabungkan CA chain ke tls_prometheus_cert_path (fullchain).",
    "tls_stapling": "ssl_stapling otomatis ON jika tls_ca_path ada di control node; paksa ON/OFF dengan enable_ssl_stapling.",
    "tls_stapling_verify": "ssl_stapling otomatis ON jika tls_ca_path ada di control node; paksa ON/OFF dengan enable_ssl_stapling.",
    "server_name": "server_name site Grafana dihitung dari grafana_domain / monitoring_vip.",
    "nginx_run_dir": "Path pid: nginx_pid_path.",
    "common_docker_network_name": "Semua container memakai --network=host; agra tidak membuat Docker network.",
    "common_docker_network_driver": "Semua container memakai --network=host; agra tidak membuat Docker network.",
    "grafana_install_method": "agra Docker-only.",
    "prometheus_native_binary_path": "agra Docker-only.",
    "prometheus_native_tools_path": "agra Docker-only (promtool dijalankan dari image Prometheus).",
    "prometheus_file_public_mode": "Mode file Prometheus: prometheus_file_mode.",
    "node_exporter_docker_user": "Container node_exporter berjalan sebagai root (--user=root) untuk membaca /proc, /sys dan /.",
    "node_exporter_file_mode": "Tidak ada file config node_exporter yang dirender.",
    # PR 11
    "prometheus_skip_head": "Owner dir/file Prometheus: prometheus_uid / prometheus_gid.",
    # Layout globals.yml sebelum PR 4–9: masih ada di /etc/agra lama karena
    # install.sh tidak pernah menimpa globals.yml.
    "agra_deployment_mode": "agra Docker-only.",
    "grafana_native_version": "agra Docker-only: versi Grafana = grafana_tag.",
    "prometheus_native_version": "agra Docker-only: versi Prometheus = prometheus_tag.",
    "node_exporter_native_version": "agra Docker-only: versi Node Exporter = node_exporter_tag.",
    "grafana_sqlite_sync_method": "Sinkronisasi SQLite antar node sudah dihapus: HA Grafana (enable_ha_grafana) wajib grafana_database mysql/postgresql eksternal.",
    "grafana_sqlite_sync_interval": "Sinkronisasi SQLite antar node sudah dihapus: HA Grafana (enable_ha_grafana) wajib grafana_database mysql/postgresql eksternal.",
    "backup_destination_type": "Backup selalu di backup_root_dir (master) lalu diambil ke backup_control_node_dir; S3 opsional lewat backup_s3_enabled.",
    "backup_destination_path": "Backup di master: backup_root_dir; salinan di control node: backup_control_node_dir.",
    "backup_retention_days": "Retensi berdasarkan jumlah: backup_retention_count (atau `agra backup create -n N`).",
    "enable_scheduled_backup": "agra tidak menjadwalkan backup; jadwalkan `agra backup create -i <inventory>` di cron control node.",
    "backup_schedule_cron": "agra tidak menjadwalkan backup; jadwalkan `agra backup create -i <inventory>` di cron control node.",
}
