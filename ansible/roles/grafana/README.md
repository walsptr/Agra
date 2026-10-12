# Role: grafana

Grafana di setiap host grup `[grafana]`, sebagai container `agra-grafana`
(image `grafana/grafana-oss`), listen `127.0.0.1:3000` di belakang nginx. Backend
database: sqlite (default, file lokal per node), mysql, atau postgresql —
keduanya database eksternal yang sudah ada (agra tidak pernah memasang
database). Datasource Prometheus lokal (UID `prometheus-main`) dan
provider dashboard JSON di-provision otomatis.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_grafana` | `true` | Set `false` untuk skip deployment Grafana |
| `enable_ha_grafana` | `false` | Semua node berbagi state lewat database eksternal (wajib mysql/postgresql) + unified alerting cluster |
| `grafana_port` | `3000` | Port listen HTTP (bind ke 127.0.0.1 jika nginx aktif, 0.0.0.0 jika `enable_nginx: false`) |
| `grafana_database` | `sqlite` | Backend DB: `sqlite` \| `mysql` \| `postgresql` |
| `grafana_admin_user` | `admin` | Username admin dashboard Grafana |
| `grafana_tag` | `11.2.0` | Docker image tag (image `grafana/grafana-oss`) |
| `grafana_server_root_url` | computed | `<scheme>://<grafana_domain \| monitoring_vip \| ansible_host node [monitoring] pertama>[:port]/` (`ansible/playbooks/vars/public_url.yml`) |
| `grafana_data_dir` | `/var/lib/agra/grafana` | Path persist data Grafana + sqlite DB |
| `grafana_prometheus_datasource_uid` | `prometheus-main` | UID datasource Prometheus (stabil untuk referensi dashboard JSON) |
| `grafana_alerting_ha_port` | `9094` | Port gossip alerting antar node saat HA |

## Contoh Penggunaan

Skenario 1: All-in-one single-node sqlite default. `/etc/agra/globals.yml` tidak perlu diubah.

Skenario 2: multi-node dengan sqlite (tanpa HA) — tiap node punya `grafana.db`
sendiri; precheck memberi warning. Dashboard dari UI tidak tersebar ke node lain.

Skenario 3: HA — semua node connect ke satu PostgreSQL eksternal (sudah ada, di luar agra):
```yaml
enable_ha_grafana: true
grafana_database: postgresql
grafana_database_host: "db.example.com"
grafana_database_name: "grafana_prod"
grafana_database_user: "grafana"
# grafana_database_password via passwords.yml field grafana_database_password
```

Sinkronisasi file SQLite antar node (rsync) sudah dihapus; role menghapus sisa
cron/script/SSH key-nya dari host lama.

Custom dashboard JSON: taruh file `.json` di `/etc/agra/config/grafana/dashboards/` — otomatis tersalin ke provisioning provider setiap deploy. Custom `grafana.ini` override via `/etc/agra/config/grafana/grafana.ini.j2`.

Password admin (`grafana_admin_password`) dipakai Grafana hanya saat database
pertama kali dibuat. Setelah itu, setiap deploy mencoba login dengan password dari
`passwords.yml` dan, jika gagal, me-reset password admin lewat stdin
(`grafana-cli admin reset-admin-password --password-from-stdin`), sehingga
password tidak terlihat di `ps`. Ganti password: ubah `passwords.yml`, lalu `agra deploy`.

Cookie sesi Grafana diberi `Secure` (`grafana_cookie_secure`) selama nginx
melayani HTTPS (`enable_nginx` dan `enable_https`).
