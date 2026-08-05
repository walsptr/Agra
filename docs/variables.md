# Variables Reference (157+)

Referensi lengkap seluruh variabel konfigurasi agra, dikelompokkan per kategori sesuai komponen. Lokasi utama:
- **Non-secret**: `/etc/agra/globals.yml`
- **Secret**: `/etc/agra/passwords.yml` (stored plaintext — chmod 0600 + included via group_vars/all.yml, sudah di .gitignore)

Konvensi penamaan:
- Flag boolean: **prefix `enable_`** (contoh: `enable_grafana`, `enable_https`)
- Versi Docker: **suffix `_tag`** (contoh: `grafana_tag`, `prometheus_tag`)
- Versi Native/Binary: **suffix `_native_version`**
- Path direktori: **suffix `_dir`** (contoh: `grafana_data_dir`)
- Path file: **suffix `_path`** (contoh: `grafana_sqlite_path`)

---

## 1. Global / Deployment Mode & Role Common

Variabel global untuk mode deployment dan preparasi host umum (role `common`).

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `agra_deployment_mode` | string | `docker` | Mode deployment global: `docker` (container) atau `native` (package/binary systemd) |
| `common_home_dir` | string | `/var/lib/agra` | Base path persist data seluruh service |
| `common_etc_dir` | string | `/etc/agra` | Direktori config agra di managed host |
| `common_os_packages` | list | see defaults | Daftar OS packages umum (rsync, openssl, curl, cron, acl, dll) di-install semua host |
| `common_firewall_tool` | string | `auto` | Tool firewall: `auto` \| `ufw` \| `firewalld` \| `none` |
| `common_firewall_ports_tcp` | list | `[]` | Port TCP tambahan yang ingin dibuka (selain dinamis dari feature flags) |
| `common_docker_package_name` | string | OS-dependent | Nama package docker: `docker.io` (Debian/Ubuntu), `docker-ce` (RedHat/Rocky) |
| `common_docker_python_sdk_package` | string | `docker` | Nama Python SDK package untuk Docker module Ansible |
| `common_podman_python_sdk_package` | string | `podman-py` | Nama Python SDK package untuk Podman (fallback jika Docker tidak tersedia) |
| `common_docker_network_name` | string | `agra_network` | Nama Docker bridge network shared antar container service |
| `common_docker_network_driver` | string | `bridge` | Driver Docker network (default: bridge untuk host-local shared) |
| `common_docker_service_name` | string | `docker` | Nama systemd service Docker |
| `common_podman_service_name` | string | `podman` | Nama systemd service Podman |

---

## 2. Grafana

Semua variabel untuk deployment Grafana (visualisasi dashboard), termasuk 3 opsi backend database dan HA sqlite sync.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_grafana` | bool | `true` | Set `false` untuk skip deployment Grafana |
| `enable_ha_grafana` | bool | `false` | Aktifkan mode sinkronisasi HA Grafana. sqlite = rsync cron multi-node; mysql/postgresql = share DB external |
| `grafana_port` | int | `3000` | Port listen HTTP Grafana (bind ke 127.0.0.1 jika nginx aktif) |
| `grafana_container_name` | string | `agra-grafana` | Nama container docker Grafana |
| `grafana_image` | string | `grafana/grafana-oss` | Docker image base untuk mode docker |
| `grafana_tag` | string | `11.2.0` | Docker image tag (mode docker) |
| `grafana_native_version` | string | `11.2.0` | Versi package atau binary release (mode native) |
| `grafana_data_dir` | string | `/var/lib/agra/grafana` | Lokasi persist data Grafana (sqlite DB, plugins, uploads) |
| `grafana_config_dir` | string | `/etc/grafana` | Lokasi config Grafana (`grafana.ini`, provisioning) |
| `grafana_provisioning_dir` | string | `{{ grafana_config_dir }}/provisioning` | Root provisioning (datasources, dashboards, plugins, notifiers) |
| `grafana_dashboards_override_dir` | string | `/etc/agra/config/grafana/dashboards` | Path override dashboard JSON user (taruh `.json` disini → auto-load) |
| `grafana_admin_user` | string | `admin` | Username admin dashboard Grafana |
| `grafana_admin_password` | string (secret) | `admin` | Password admin dashboard → ref passwords.yml field `grafana_admin_password` (override default "admin") |
| `grafana_database` | string | `sqlite` | Backend database: `sqlite` \| `mysql` \| `postgresql` |
| `grafana_database_ssl_mode` | string | `disable` | SSL mode koneksi DB: `disable` \| `require` \| `verify-ca` \| `verify-full` |
| `grafana_database_host` | string | `""` | Host/IP database (WAJIB diisi jika mysql/postgresql. DB external yang sudah ada — agra TIDAK install DB) |
| `grafana_database_port` | int (computed) | conditional | 3306 (mysql), 5432 (postgresql), 0 (sqlite) |
| `grafana_database_name` | string | `grafana` | Nama database |
| `grafana_database_user` | string | `grafana` | User database |
| `grafana_database_password` | string (secret) | `""` | Password database → ref passwords.yml field `grafana_database_password` |
| `grafana_sqlite_path` | string | `{{ grafana_data_dir }}/grafana.db` | Path absolute file sqlite database |
| `grafana_sqlite_sync_method` | string | `rsync` | Metode sinkronisasi sqlite antar node untuk HA |
| `grafana_sqlite_sync_interval` | string | `*/5 * * * *` | Cron expression interval sync (default tiap 5 menit) |
| `grafana_sqlite_sync_ssh_user` | string | `root` | SSH user untuk koneksi rsync antar node monitoring |
| `grafana_server_domain` | string | `{{ inventory_hostname }}` | Domain/hostname server Grafana (untuk callback URL dll) |
| `grafana_server_root_url` | string (computed) | conditional | Root URL full. Otomatis pakai `monitoring_vip` jika HA, else host+port via nginx |
| `grafana_server_protocol` | string | `http` | Protocol internal backend Grafana (http/https). HTTPS di-terminate oleh Nginx. |
| `grafana_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `grafana_secret_key` | string (secret) | `CHANGE_ME_GRAFANA_SECRET_KEY_MIN_32_CHARS` | Secret key untuk signing session, CSRF, remember cookie → ref passwords.yml field `grafana_secret_key` |
| `grafana_web_listen_address` | string (computed) | conditional | Bind address. `127.0.0.1:3000` jika Nginx aktif (recommended), else `0.0.0.0:3000` |
| `grafana_prometheus_datasource_name` | string | `Prometheus` | Nama display datasource Prometheus di UI Grafana |
| `grafana_prometheus_datasource_uid` | string | `prometheus-main` | UID datasource stabil (untuk referensi di dashboard JSON via `uid`) |
| `grafana_prometheus_datasource_url` | string | `http://127.0.0.1:{{ prometheus_port }}` | URL upstream Prometheus untuk datasource (internal via localhost) |
| `grafana_install_method` | string | `binary` | Fallback metode install native (pakai tar.gz binary resmi) |

---

## 3. Prometheus

Variabel untuk Prometheus server (TSDB + scraper metrics). Admin API selalu aktif untuk snapshot backup TSDB resmi.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_prometheus` | bool | `true` | Set `false` untuk skip deployment Prometheus |
| `prometheus_port` | int | `9090` | Port listen HTTP UI + API |
| `prometheus_retention_time` | string | `15d` | Retensi TSDB berbasis waktu (format: 15d, 6h, 1y) |
| `prometheus_retention_size` | string | `""` | Opsional retensi berbasis ukuran storage (contoh: `50GB`). Yang tercapai duluan yang aktif. |
| `prometheus_scrape_interval` | string | `15s` | Global default interval scrape target |
| `prometheus_evaluation_interval` | string | `15s` | Interval evaluasi recording rule + alerting rule |
| `prometheus_data_dir` | string | `/var/lib/agra/prometheus` | Lokasi persist data TSDB (TIDAK di-purge default saat destroy) |
| `prometheus_config_dir` | string | `/etc/prometheus` | Lokasi config Prometheus |
| `prometheus_file_sd_dir` | string | `{{ prometheus_config_dir }}/file_sd` | Lokasi file service discovery auto-generate dari inventory |
| `prometheus_rules_dir` | string | `{{ prometheus_config_dir }}/rules` | Lokasi recording rule dan alerting rule YAML |
| `prometheus_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `prometheus_image` | string | `prom/prometheus` | Docker image Prometheus |
| `prometheus_tag` | string | `v2.53.0` | Docker image tag |
| `prometheus_container_name` | string | `agra-prometheus` | Nama container docker |
| `prometheus_native_version` | string | `2.53.0` | Versi binary release Prometheus |
| `prometheus_native_binary_path` | string | `/usr/local/bin/prometheus` | Path absolute binary Prometheus (mode native) |
| `prometheus_native_binary_url` | string | URL github | Template URL download tarball release (mengandung `{{version}}`) |
| `prometheus_native_tools_path` | string | `/usr/local/bin/promtool` | Path binary promtool (untuk validasi config/rules offline) |
| `prometheus_web_external_url` | string | `""` | Opsional external URL untuk link generation di alert dan UI |
| `prometheus_web_listen_address` | string (computed) | conditional | Bind: `127.0.0.1:9090` jika nginx aktif tanpa expose, else `0.0.0.0:9090` |
| `prometheus_skip_head` | string | `65534` | UID user `nobody` untuk ownership TSDB dir + docker container user (security) |
| `expose_prometheus_via_nginx` | bool | `false` | Expose Prometheus UI publik via Nginx path `/prometheus/`. Default `false` = return 403 (Prometheus default tanpa auth!) |

> Catatan: Tidak ada `enable_ha_prometheus`. Ketahanan Prometheus murni konsekuensi jumlah host di `groups['monitoring']` (full duplication). `--web.enable-admin-api` SELALU aktif untuk snapshot TSDB backup resmi.

---

## 4. Node Exporter

Variabel untuk Prometheus Node Exporter — mengekspor OS & hardware metrics ke endpoint `/metrics`.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_node_exporter` | bool | `true` | Set `false` untuk skip deployment Node Exporter |
| `node_exporter_port` | int | `9100` | Port listen HTTP endpoint `/metrics` |
| `node_exporter_image` | string | `prom/node-exporter` | Docker image Node Exporter |
| `node_exporter_tag` | string | `v1.8.2` | Docker image tag |
| `node_exporter_native_version` | string | `1.8.2` | Versi binary release (mode native) |
| `node_exporter_collectors_enabled` | list | `[]` | Collector tambahan diaktifkan (contoh: `['systemd','interrupts','tcpstat']`) → `--collector.<nama>` |
| `node_exporter_collectors_disabled` | list | `[]` | Collector default dimatikan (contoh: `['arp','mdadm']`) → `--no-collector.<nama>` |
| `node_exporter_textfile_dir` | string | `""` | Direktori custom untuk textfile collector (opsional; isi suffix `_key="*.prom"` flag) |
| `node_exporter_config_dir` | string | `/etc/node_exporter` | Direktori config Node Exporter di managed host |
| `node_exporter_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `node_exporter_container_name` | string | `agra-node-exporter` | Nama container docker |
| `node_exporter_native_binary_path` | string | `/usr/local/bin/node_exporter` | Path absolute binary (mode native) |
| `node_exporter_native_binary_url` | string | URL github | Template URL download tarball release (mengandung `{{version}}`) |
| `node_exporter_web_listen_address` | string | `0.0.0.0:{{ node_exporter_port }}` | Bind address — default semua interface (karena di-scrape internal oleh Prometheus) |

> Catatan: Tidak ada konsep HA untuk Node Exporter (exporter pasif). Ketahanan mengikuti Prometheus yang men-scrape dia.

---

## 5. Keepalived (Monitoring VIP / HA)

Keepalived untuk Virtual IP (VRRP v2) cluster monitoring multi-node. **Otomatis aktif ketika `groups['monitoring']|length > 1`** (topology-driven), tidak perlu set `enable_keepalived: true` secara eksplisit.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_keepalived` | bool (computed) | `groups['monitoring']|length > 1` | Hanya untuk **force-disable manual**. Normalnya otomatis dari inventory. Set `false` di globals.yml untuk men-disable VIP meskipun multi-node. |
| `monitoring_vip` | string | `""` | Virtual IP address tunggal untuk Grafana + Prometheus + Nginx. **WAJIB diisi jika monitoring > 1 node.** User akses: `https://<monitoring_vip>/grafana` |
| `monitoring_vip_interface` | string | computed | Interface network untuk bind VIP. Default: `ansible_default_ipv4.interface` → fallback `eth0` |
| `keepalived_router_id` | int | `51` | VRRP virtual router ID 0-255. **HARUS UNIK** antar VRRP cluster di segmen L2 yang sama. |
| `keepalived_vrrp_instance` | string | `VI_MONITORING_01` | Nama VRRP instance di keepalived.conf |
| `keepalived_auth_pass` | string (secret) | `""` | Password autentikasi VRRP (plaintext) → ref passwords.yml field `keepalived_auth_pass` |
| `keepalived_check_interval` | int | `2` | Interval health check (detik) |
| `keepalived_fall_count` | int | `3` | Jumlah kegagalan berturut-turut sebelum node dianggap unhealthy → VIP pindah |
| `keepalived_rise_count` | int | `2` | Jumlah sukses berturut sebelum node dianggap sehat kembali |
| `keepalived_weight` | int | `-20` | Pengurangan priority bila `track_script` gagal |
| `keepalived_script_name` | string | `chk_agra_monitoring` | Nama `vrrp_script` di keepalived.conf |
| `keepalived_log_file` | string | `/var/log/agra-keepalived.log` | File log healthcheck + notify script keepalived |
| `keepalived_config_dir` | string | `/etc/keepalived` | Direktori config keepalived (mode native) |
| `keepalived_container_name` | string | `agra-keepalived` | Nama container docker keepalived |
| `keepalived_priority` | int (computed) | formula | Priority VRRP per host: `groups['monitoring'][0]` = 201 (MASTER), `idx=1` = 101 (BACKUP), dst. Formula: `201 - idx*100` |
| `keepalived_state` | string (computed) | MASTER/BACKUP | `MASTER` jika host == `groups['monitoring'][0]`, else `BACKUP`. Deterministik dari inventory order. |
| `grafana_health_url` | string | `http://127.0.0.1:{{grafana_port}}/api/health` | Endpoint health check Grafana untuk combined vrrp_script |
| `prometheus_health_url` | string | `http://127.0.0.1:{{prometheus_port}}/-/healthy` | Endpoint health check Prometheus untuk combined vrrp_script |
| `nginx_health_url` | string | `http://127.0.0.1/healthz` | Endpoint health check Nginx (reserved, future use) |
| `keepalived_native_package_name` | string | `keepalived` | Nama OS package keepalived (native mode) |
| `keepalived_service_name` | string | `keepalived` | Nama systemd service keepalived (native mode) |
| `keepalived_image` | string | `osixia/keepalived` | Docker image keepalived (docker mode) |
| `keepalived_tag` | string | `"2.0.20"` | Docker image tag keepalived |

---

## 6. Nginx / TLS

Reverse proxy Nginx frontend untuk Grafana (path `/grafana/` atau `/`) + optional Prometheus (path `/prometheus/`). Default native OS package install.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_nginx` | bool | `true` | Set `false` skip Nginx (service langsung expose port — TIDAK DISARANKAN production) |
| `enable_https` | bool | `true` | Aktifkan HTTPS port 443. HTTP 80 → redirect permanen 301 ke HTTPS. |
| `expose_prometheus_via_nginx` | bool | `false` | Expose Prometheus UI via `/prometheus/`. Default `false` = return 403 (Prometheus default tanpa auth) |
| `nginx_container_name` | string | `agra-nginx` | Nama container docker nginx |
| `nginx_image` | string | `nginx` | Docker image Nginx |
| `nginx_tag` | string | `1.27-alpine` | Docker image tag (hanya mode docker — default nginx pakai native) |
| `nginx_native_version` | string | `""` | Versi package native. `""` = latest dari repo OS |
| `nginx_install_method` | string | `native` | Default install method (native preferred untuk reverse proxy production) |
| `nginx_config_dir` | string | `/etc/nginx` | Root config Nginx |
| `nginx_sites_available_dir` | string | `{{ nginx_config_dir }}/sites-available` | Debian-style sites-available directory |
| `nginx_sites_enabled_dir` | string | `{{ nginx_config_dir }}/sites-enabled` | Debian-style sites-enabled (symlink ke sites-available) |
| `nginx_confd_dir` | string | `{{ nginx_config_dir }}/conf.d` | conf.d include directory (drop-in configs) |
| `nginx_log_dir` | string | `/var/log/nginx` | Lokasi log access dan error |
| `nginx_cache_dir` | string | `/var/cache/nginx` | Lokasi cache/proxy temp files |
| `nginx_run_dir` | string | `/var/run` | Run directory untuk PID |
| `nginx_pid_path` | string | `/var/run/nginx.pid` | Path absolute PID file Nginx |
| `nginx_worker_processes` | string | `auto` | Worker processes (auto = 1 per CPU core) |
| `nginx_worker_connections` | int | `1024` | Max koneksi simultan per worker process |
| `nginx_keepalive_timeout` | int | `65` | Keepalive timeout dalam detik |
| `nginx_client_max_body_size` | string | `25m` | Max ukuran request body (untuk upload dashboard, dll) |
| `tls_self_signed_generate` | bool | `true` | Auto-generate self-signed cert jika custom cert tidak ada (dengan `creates:` guard → idempotent) |
| `tls_self_signed_cn` | string | computed | Common Name cert: `monitoring_vip` jika ada, else `inventory_hostname` |
| `tls_self_signed_days_valid` | int | `3650` | Masa berlaku self-signed cert (default 10 tahun) |
| `tls_self_signed_country` | string | `ID` | Subject C (Country) |
| `tls_self_signed_state` | string | `Jakarta` | Subject ST (State/Provinsi) |
| `tls_self_signed_locality` | string | `Jakarta` | Subject L (Locality/Kota) |
| `tls_self_signed_organization` | string | `agra-monitoring` | Subject O (Organization) |
| `tls_self_signed_organizational_unit` | string | `it` | Subject OU (Organizational Unit) |
| `tls_cert_path` | string | `/etc/agra/ssl/agra.crt` | Path certificate (default = pre-deploy control node via `agra certificates generate`). Override untuk CA-signed custom. |
| `tls_key_path` | string | `/etc/agra/ssl/agra.key` | Path private key |
| `tls_ca_path` | string | `/etc/agra/ssl/agra-ca.crt` | Path CA chain certificate (opsional) |
| `tls_dhparam_path` | string | `/etc/agra/ssl/dhparam.pem` | Path Diffie-Hellman parameters untuk forward secrecy DHE (generate via `agra certificates generate --include-dhparam`) |
| `tls_dhparam_bits` | int | `2048` | Panjang bit DH param (2048 = balance keamanan & waktu generate) |
| `tls_protocols` | string | `TLSv1.2 TLSv1.3` | Protokol TLS yang diizinkan (TLS 1.0/1.1 disable default) |
| `tls_ciphers` | string | ECDHE-only | Cipher suite ECDHE-only untuk forward secrecy (lihat defaults untuk string lengkap) |
| `tls_prefer_server_ciphers` | string | `on` | Prioritaskan cipher order server daripada client |
| `tls_session_timeout` | string | `1d` | Timeout SSL session cache |
| `tls_session_cache` | string | `shared:SSL:10m` | SSL session cache shared memory 10MB |
| `tls_session_tickets` | string | `off` | Disable TLS session tickets (PFS lebih baik tanpa ticket key rotation manual) |
| `tls_stapling` | string | `on` | OCSP stapling (hanya berlaku untuk cert CA-signed) |
| `tls_stapling_verify` | string | `on` | Verifikasi OCSP response validity |
| `tls_hsts_max_age` | string | `31536000` | HSTS max-age (1 tahun = 31536000 detik) |
| `tls_hsts_include_subdomains` | bool | `true` | HSTS includeSubDomains directive |
| `tls_hsts_preload` | bool | `false` | HSTS preload (false = tidak otomatis submit ke browser preload list) |
| `grafana_backend_url` | string | `http://127.0.0.1:{{ grafana_port \| default(3000) }}` | Upstream reverse proxy internal ke Grafana (bind localhost) |
| `prometheus_backend_url` | string | `http://127.0.0.1:{{ prometheus_port \| default(9090) }}` | Upstream reverse proxy internal ke Prometheus |
| `server_name` | string | computed | Nginx `server_name` directive. Default = `{{monitoring_vip|default(inventory_hostname)}} _` (catch-all) |
| `nginx_http_port` | int | `80` | Port HTTP listener (redirect ke HTTPS) |
| `nginx_https_port` | int | `443` | Port HTTPS listener |

> Tips custom cert CA-signed: Taruh `agra.crt` (fullchain), `agra.key` (privkey), opsional `agra-ca.crt` di folder `/etc/agra/config/nginx/ssl/` (control node sebelum deploy, atau remote di managed host). Config.yml otomatis copy ke `/etc/nginx/ssl/` tanpa overwrite self-signed generate.

---

## 7. Backup & Restore

Backup local-first (default), opsional mirror ke S3-compatible object storage.

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `backup_destination_type` | string | `local` | Tipe destination: `local` \| `s3` |
| `backup_destination_path` | string | `/var/backups/agra` | Path folder backup di **control node** (bukan managed host) |
| `backup_retention_days` | int | `14` | Retensi backup (dihapus otomatis jika lebih tua dari ini) |
| `backup_include_prometheus_tsdb` | bool | `false` | Sertakan snapshot TSDB Prometheus. Default OFF karena ukuran bisa sangat besar. WAJIB pakai snapshot Admin API resmi — TIDAK PERNAH tar folder TSDB langsung. |
| `backup_s3_enabled` | bool | `false` | Aktifkan mirror backup ke S3 setelah backup lokal selesai & tervalidasi (local-first principle) |
| `backup_s3_bucket` | string | `""` | Nama bucket S3 |
| `backup_s3_endpoint` | string | `""` | Endpoint S3-compatible. Kosong = AWS S3 standar; isi untuk MinIO, Cloudflare R2, dll |
| `backup_s3_region` | string | `""` | Region S3 (AWS) |
| `backup_s3_access_key` | string (secret) | `""` | Access key S3 → ref passwords.yml field `backup_s3_access_key` |
| `backup_s3_secret_key` | string (secret) | `""` | Secret key S3 → ref passwords.yml field `backup_s3_secret_key` |
| `enable_scheduled_backup` | bool | `false` | Aktifkan backup terjadwal via cron di control node |
| `backup_schedule_cron` | string | `0 2 * * *` | Jadwal cron backup otomatis (default: jam 2 pagi setiap hari) |

---

## 8. Passwords

Semua variabel di bawah ini **didefinisikan di `/etc/agra/passwords.yml`** dalam format plaintext dengan chmod 0600 (hanya owner bisa baca). File ini SUDAH termasuk di `.gitignore` — JANGAN commit plaintext ke git. Variabel dari `passwords.yml` dioverride ke `globals.yml` dan role defaults secara otomatis oleh `group_vars/all.yml` (priority inventory > role defaults).

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `grafana_admin_password` | string (secret) | generate via `agra genpwd` (14 chars) | Password login admin dashboard Grafana |
| `grafana_database_password` | string (secret) | generate via `agra genpwd` (14 chars) | Password koneksi database Grafana (untuk backend mysql/postgresql external) |
| `grafana_secret_key` | string (secret) | generate via `agra genpwd` (14 chars) | Secret key signing: session cookie, CSRF token, remember-me cookie |
| `keepalived_auth_pass` | string (secret) | generate via `agra genpwd` (14 chars) | Password autentikasi VRRP keepalived (antar node monitoring cluster) |
| `backup_s3_access_key` | string (secret) | generate via `agra genpwd` (14 chars) | Access key credential untuk S3 backup mirror |
| `backup_s3_secret_key` | string (secret) | generate via `agra genpwd` (14 chars) | Secret key credential untuk S3 backup mirror |
