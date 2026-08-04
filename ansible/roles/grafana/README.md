# Role: grafana

Deploy Grafana (visualisasi dashboard monitoring) dengan hybrid deployment mode: Docker container atau native install. Mendukung 3 backend database: sqlite (default, file embedded), mysql, postgresql (kedua terakhir connect ke DB external — RULES.md §9: agra TIDAK PERNAH install/provisioning DB). Include auto-provisioning datasource Prometheus UID `prometheus-main` dan dashboard provider dari JSON file.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_grafana` | `true` | Set `false` untuk skip deployment Grafana |
| `enable_ha_grafana` | `false` | Aktifkan HA mode (sync sqlite via rsync cron multi-node, atau share DB external) |
| `grafana_port` | `3000` | Port listen HTTP (bind ke 127.0.0.1 jika nginx aktif) |
| `grafana_database` | `sqlite` | Backend DB: `sqlite` \| `mysql` \| `postgresql` |
| `grafana_admin_user` | `admin` | Username admin dashboard Grafana |
| `grafana_tag` | `11.2.0` | Docker image tag (mode docker: image `grafana/grafana-oss`) |
| `grafana_native_version` | `11.2.0` | Versi package (mode native) |
| `grafana_server_root_url` | computed | Root URL otomatis: `monitoring_vip` jika HA, atau host+port |
| `grafana_data_dir` | `/var/lib/agra/grafana` | Path persist data Grafana + sqlite DB |
| `grafana_prometheus_datasource_uid` | `prometheus-main` | UID datasource Prometheus (stabil untuk referensi dashboard JSON) |
| `grafana_sqlite_sync_interval` | `*/5 * * * *` | Cron expression interval rsync sqlite HA (multi-node dengan sqlite backend) |

## Contoh Penggunaan

Skenario 1: All-in-one single-node sqlite default. `globals.yml` tidak perlu diubah.

Skenario 2: HA multi-node dengan sqlite sync:
```yaml
enable_ha_grafana: true
grafana_database: sqlite
grafana_sqlite_sync_interval: "*/2 * * * *"
monitoring_vip: "10.0.0.100"
```

Skenario 3: Connect ke external PostgreSQL (DB sudah ada, diluar agra):
```yaml
enable_ha_grafana: true
grafana_database: postgresql
grafana_database_host: "db.example.com"
grafana_database_port: 5432
grafana_database_name: "grafana_prod"
grafana_database_user: "grafana"
# grafana_database_password via passwords.yml field grafana_database_password
```

Custom dashboard JSON: taruh file `.json` di `/etc/agra/config/grafana/dashboards/` — otomatis tersalin ke provisioning provider setiap deploy. Custom `grafana.ini` override via `/etc/agra/config/grafana/grafana.ini.j2`.

Lihat contexts/DESIGN.md untuk pola router config+docker+native.
