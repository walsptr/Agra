# SCHEMA.md — agra

Referensi lengkap seluruh variabel konfigurasi agra. Setiap penambahan
variabel baru WAJIB langsung diupdate di sini (lihat RULES.md §12).

Lokasi utama: **`/etc/agra/globals.yml` absolute path di control node** = SATU-SATUNYA SUMBER (single source of truth) vars konfigurasi fitur/versi untuk precheck assertion. JANGAN set vars konfigurasi (selain vars koneksi SSH murni seperti ansible_host/ansible_user/ansible_port) di file inventory `[group:vars]` atau Ansible host_vars; perubahan hanya akan dibaca oleh playbook precheck & deploy jika ada di `/etc/agra/globals.yml`. Lihat RULES.md §14 untuk kategori vars koneksi vs vars konfigurasi. Template default source untuk di-copy user saat install ada di repo: `./etc/agra/globals.yml`. Passwords di `/etc/agra/passwords.yml` (secret, wajib di-vault).

---

## 1. Role Common (Preparasi Host)

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `common_home_dir` | string | `/var/lib/agra` | Base persist data directory |
| `common_etc_dir` | string | `/etc/agra` | Direktori config agra di managed host |
| `common_os_packages` | list | see defaults | Daftar OS packages umum (rsync, openssl, curl, cron, acl, dll) |
| `common_firewall_tool` | string | `auto` | `auto` \| `ufw` \| `firewalld` \| `none` — tool firewall yang dipakai |
| `common_firewall_ports_tcp` | list | `[]` | Port TCP tambahan yang ingin dibuka (selain dinamis dari feature flags) |
| `common_docker_package_name` | string | OS-dependent | Nama package docker (docker.io untuk Debian, docker-ce untuk RedHat) |
| `common_docker_python_sdk_package` | string | `docker` | Nama Python SDK package untuk Docker |
| `common_podman_python_sdk_package` | string | `podman-py` | Nama Python SDK package untuk Podman (fallback) |
| `common_docker_network_name` | string | `agra_network` | Nama Docker network bridge shared antar container service |
| `common_docker_network_driver` | string | `bridge` | Driver Docker network (default: bridge) |
| `common_docker_service_name` | string | `docker` | Nama systemd service Docker |
| `common_podman_service_name` | string | `podman` | Nama systemd service Podman |

## 2. Grafana

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `enable_grafana` | bool | `true` | Aktifkan deployment Grafana |
| `enable_ha_grafana` | bool | `false` | Aktifkan mode HA (syarat: `groups['monitoring'] >= 2`) |
| `grafana_port` | int | `3000` | Port listen Grafana di dalam container (internal bind 127.0.0.1 di dalam node, tidak di-expose publik langsung ke node) |
| `grafana_container_name` | string | `agra-grafana` | Nama container docker |
| `grafana_image` | string | `grafana/grafana-oss` | Docker image (mode docker) |
| `grafana_tag` | string | `11.2.0` | Docker image tag (mode docker) |

| `grafana_data_dir` | string | `/var/lib/agra/grafana` | Lokasi data persist |
| `grafana_config_dir` | string | `/etc/grafana` | Lokasi config Grafana |
| `grafana_provisioning_dir` | string | `{{ grafana_config_dir }}/provisioning` | Lokasi provisioning (datasources/dashboards) |
| `grafana_dashboards_override_dir` | string | `/etc/agra/config/grafana/dashboards` | Path override dashboard JSON user |
| `grafana_admin_user` | string | `admin` | Username admin Grafana |
| `grafana_admin_password` | string (secret) | vault ref | Password admin dashboard, via `vault_grafana_admin_password` |
| `grafana_database` | string | `sqlite` | `sqlite` \| `mysql` \| `postgresql` |
| `grafana_database_ssl_mode` | string | `disable` | `disable` \| `require` \| `verify-ca` \| `verify-full` |
| `grafana_database_host` | string | `""` | Wajib diisi jika `grafana_database` mysql/postgresql (eksternal) |
| `grafana_database_port` | jinja computed | conditional | 3306 (mysql) / 5432 (postgresql) / 0 (sqlite) |
| `grafana_database_name` | string | `grafana` | Nama database |
| `grafana_database_user` | string | `grafana` | User database |
| `grafana_database_password` | string (secret) | vault ref | Ref ke `vault_grafana_database_password` |
| `grafana_sqlite_path` | string | `{{ grafana_data_dir }}/grafana.db` | Path file sqlite DB |
| `grafana_sqlite_sync_method` | string | `rsync` | Metode sinkronisasi sqlite antar node saat HA |
| `grafana_sqlite_sync_interval` | string | `*/5 * * * *` | Cron expression interval sync sqlite |
| `grafana_sqlite_sync_ssh_user` | string | `root` | SSH user untuk rsync sync sqlite |
| `grafana_server_domain` | string | `{{ inventory_hostname }}` | Domain server Grafana (internal value — nilai **publik** untuk `server_name` di nginx pakai `grafana_domain` + `monitoring_vip`) |
| `grafana_server_root_url` | jinja computed | conditional | Root URL Grafana di path root `/` (tanpa subpath `/grafana/`). Otomatis pakai https://<monitoring_vip>/ jika ada, else https://<host>/ (nginx aktif) atau http://<host>:3000/ (direct tanpa nginx). serve_from_sub_path=false (serve root) |
| `grafana_server_protocol` | string | `http` | Protocol server (http/https) |
| `grafana_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `grafana_secret_key` | string (secret) | vault ref | Secret key untuk signing, via `vault_grafana_secret_key` |
| `grafana_domain` | string | `""` | Custom domain expose Grafana HTTPS (mis. `monitor.example.com`). Bersama `monitoring_vip` menjadi 2 value utama nginx `server_name` public (TIDAK include hostname node). |
| `grafana_nginx_port` | int | `30080` | Port Nginx listen untuk expose Grafana ke publik ketika `grafana_domain` kosong (akses via http://<node-ip>:30080 tanpa domain). |
| `grafana_web_listen_address` | jinja computed | conditional | Bind address: `127.0.0.1:3000` (nginx aktif) / `0.0.0.0:3000` (direct) |
| `grafana_prometheus_datasource_name` | string | `Prometheus` | Nama display datasource Prometheus |
| `grafana_prometheus_datasource_uid` | string | `prometheus-main` | UID datasource Prometheus (stabil) |
| `grafana_prometheus_datasource_url` | string | `http://127.0.0.1:{{ prometheus_port }}` | URL datasource Prometheus |
| `grafana_install_method` | string | `binary` | Metode install native fallback |

## 3. Prometheus

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `enable_prometheus` | bool | `true` | Aktifkan deployment Prometheus |
| `prometheus_port` | int | `9090` | Port listen Prometheus di dalam container (internal bind 127.0.0.1) |
| `prometheus_retention_time` | string | `15d` | Retensi data TSDB (time-based) |
| `prometheus_retention_size` | string | `""` | Opsional retensi berbasis size, mis. `50GB` |
| `prometheus_scrape_interval` | string | `15s` | Interval scrape default global |
| `prometheus_evaluation_interval` | string | `15s` | Interval evaluasi alerting/recording rule |
| `prometheus_data_dir` | string | `/var/lib/agra/prometheus` | Lokasi data persist TSDB |
| `prometheus_config_dir` | string | `/etc/prometheus` | Lokasi config Prometheus |
| `prometheus_file_sd_dir` | string | `{{ prometheus_config_dir }}/file_sd` | Lokasi file_sd target auto-generate |
| `prometheus_rules_dir` | string | `{{ prometheus_config_dir }}/rules` | Lokasi recording/alerting rules |
| `prometheus_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `prometheus_image` | string | `prom/prometheus` | Docker image (mode docker) |
| `prometheus_tag` | string | `v2.53.0` | Docker image tag (mode docker) |
| `prometheus_container_name` | string | `agra-prometheus` | Nama container docker |

| `prometheus_native_binary_path` | string | `/usr/local/bin/prometheus` | Path binary prometheus (native) |
| `prometheus_native_binary_url` | string | URL github | URL download tarball release Prometheus |
| `prometheus_native_tools_path` | string | `/usr/local/bin/promtool` | Path binary promtool (validasi config) |
| `prometheus_web_external_url` | string | `""` | Opsional external URL untuk link generation |
| `prometheus_web_listen_address` | string | computed | Bind address: `127.0.0.1:9090` jika nginx aktif tanpa expose, else `0.0.0.0:9090` |
| `prometheus_skip_head` | string | `65534` | UID user nobody untuk ownership TSDB dir + docker container user |
| `expose_prometheus_via_nginx` | bool | `false` | Expose Prometheus UI publik lewat Nginx path `/prometheus/` |
| `prometheus_domain` | string | `""` | Domain dedicated expose Prometheus HTTPS (mis. `prom.example.com`). Jika diisi → expose dianggap true & dedicated server block dibuat; ssl cert bisa dedicated via `tls_prometheus_cert_path`; fallback empty = expose via `/prometheus` subpath |
| `prometheus_nginx_port` | int | `30090` | Port Nginx listen untuk expose Prometheus ke publik ketika `prometheus_domain` kosong (akses via http://<node-ip>:30090 tanpa domain). |

Catatan: Tidak ada `enable_ha_prometheus`. Ketahanan Prometheus murni
konsekuensi jumlah host di `groups['monitoring']`/`groups['prometheus']`.
`--web.enable-admin-api` SELALU aktif untuk snapshot API backup TSDB resmi.

## 4. Node Exporter

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `enable_node_exporter` | bool | `true` | Aktifkan deployment Node Exporter |
| `node_exporter_port` | int | `9100` | Port listen |
| `node_exporter_image` | string | `prom/node-exporter` | Docker image (mode docker) |
| `node_exporter_tag` | string | `v1.8.2` | Docker image tag (mode docker) |

| `node_exporter_collectors_enabled` | list | `[]` | Collector tambahan yang diaktifkan (--collector.) |
| `node_exporter_collectors_disabled` | list | `[]` | Collector default yang dimatikan (--no-collector.) |
| `node_exporter_textfile_dir` | string | `""` | Direktori textfile collector custom (opsional) |
| `node_exporter_config_dir` | string | `/etc/node_exporter` | Direktori config Node Exporter di managed host |
| `node_exporter_log_level` | string | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |
| `node_exporter_container_name` | string | `agra-node-exporter` | Nama container docker Node Exporter |
| `node_exporter_native_binary_path` | string | `/usr/local/bin/node_exporter` | Path binary Node Exporter (mode native) |
| `node_exporter_native_binary_url` | string | URL github | URL download tarball release Node Exporter (mode native, template {{version}}) |
| `node_exporter_web_listen_address` | string | `0.0.0.0:{{ node_exporter_port }}` | Bind address listener Node Exporter (default: semua interface karena di-scrape internal Prometheus) |

Catatan: Tidak ada konsep HA untuk Node Exporter.

## 5. Monitoring VIP / Keepalived

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `enable_keepalived` | bool (computed) | `groups['monitoring']\|length > 1` | **Hanya untuk force-disable manual**. Normalnya otomatis dari inventory multi-node. Set `false` di globals.yml untuk men-disable meskipun multi-node. (ARCHITECTURE §5.1, DESIGN §4) |
| `monitoring_vip` | string | `""` | VIP untuk akses Grafana+Prometheus+Nginx, wajib diisi jika `groups['monitoring'] > 1` (HANYA di-set di **`/etc/agra/globals.yml` absolute path control node**; jika multi-node HA wajib isi variable di file ini. DILARANG set via inventory `[monitoring:vars]` atau host_vars/* — precheck assertion tidak akan membaca value dari sumber apapun selain direct parse globals.yml). Lihat RULES.md §14. |
| `monitoring_vip_interface` | string | `ansible_default_ipv4.interface` | Interface network untuk VIP (default=interface utama host, fallback `eth0`) |
| `keepalived_router_id` | int | `51` | VRRP virtual router ID (0-255, UNIK antar VRRP cluster di segmen yang sama) |
| `keepalived_vrrp_instance` | string | `VI_MONITORING_01` | Nama VRRP instance di keepalived.conf |
| `keepalived_auth_pass` | string (secret) | Default "A9ra!P4s" NON-SECRET placeholder | Keepalived VRRP auth_pass type "PASS" (Keepalived v2.0 MAX 8 KARAKTER HARD LIMIT!). GENERATE OLEH `agra genpwd` = 14 karakter (14 chars password complexity) — template guard keepalived.conf.j2 OTOMATIS truncate ke 8 karakter pertama. Default value placeholder NON SECRET. PRODUCTION: OVERRIDE di passwords.yml (vault encrypted via ansible-vault, RULES §7). JANGAN SET EMPTY STRING (akan cause CONFIG PARSE FATAL L37 auth_pass missing parameter). |
| `keepalived_check_interval` | int | `2` | Interval health check (detik) |
| `keepalived_fall_count` | int | `3` | Jumlah gagal berturut sebelum failover |
| `keepalived_rise_count` | int | `2` | Jumlah sukses berturut sebelum dianggap pulih |
| `keepalived_weight` | int | `-20` | Weight pengurangan priority jika track_script gagal |
| `keepalived_script_name` | string | `chk_agra_monitoring` | Nama `vrrp_script` di keepalived.conf |
| `keepalived_log_file` | string | `/var/log/agra-keepalived.log` | File log healthcheck + notify script keepalived |
| `keepalived_config_dir` | string | `/etc/keepalived` | Direktori config keepalived (mode native) |
| `keepalived_container_name` | string | `agra-keepalived` | Nama container docker keepalived |
| `keepalived_priority` | int (computed) | formula 201-idx\*100 | Priority VRRP: `groups['monitoring'][0]`=201 (MASTER), idx=1=101 (BACKUP), dst. (DESIGN §4) |
| `keepalived_state` | string (computed) | MASTER/BACKUP | `MASTER` jika host == `groups['monitoring'][0]`, else `BACKUP` (DESIGN §4 deterministik) |
| `grafana_health_url` | string | `http://127.0.0.1:{{grafana_port}}/api/health` | Endpoint health check Grafana untuk combined vrrp_script |
| `prometheus_health_url` | string | `http://127.0.0.1:{{prometheus_port}}/-/healthy` | Endpoint health check Prometheus untuk combined vrrp_script |
| `nginx_health_url` | string | `http://127.0.0.1/healthz` | Endpoint health check Nginx (reserved, future use) |

| `keepalived_image` | string | `osixia/keepalived` | Docker image keepalived (docker mode) |
| `keepalived_tag` | string | `"2.0.20"` | Docker image tag keepalived (docker mode) |

Catatan: Role keepalived **otomatis aktif** jika `groups['monitoring'] | length > 1`
(topology-driven, ARCHITECTURE §5.1). `enable_keepalived` HANYA untuk force-disable
manual — tidak ada workflow normal yang menset flag ini ke true/false secara
eksplisit. Single-node → role `meta: end_host` (idempotent skip, no-op).

## 6. Nginx / TLS

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `enable_nginx` | bool | `true` | Aktifkan reverse proxy Nginx |
| `enable_https` | bool | `true` | Aktifkan HTTPS (self-signed default) |
| `expose_prometheus_via_nginx` | bool | `false` | Expose Prometheus UI publik lewat Nginx path `/prometheus/`; default false = return 403 |
| `nginx_container_name` | string | `agra-nginx` | Nama container docker |
| `nginx_image` | string | `nginx` | Docker image (mode docker) |
| `nginx_tag` | string | `1.27-alpine` | Docker image tag (mode docker) |

| `nginx_config_dir` | string | `/etc/nginx` | Lokasi config nginx |
| `nginx_sites_available_dir` | string | `{{ nginx_config_dir }}/sites-available` | Debian-style sites-available |
| `nginx_sites_enabled_dir` | string | `{{ nginx_config_dir }}/sites-enabled` | Debian-style sites-enabled |
| `nginx_confd_dir` | string | `{{ nginx_config_dir }}/conf.d` | conf.d include dir |
| `nginx_log_dir` | string | `/var/log/nginx` | Lokasi log |
| `nginx_cache_dir` | string | `/var/cache/nginx` | Lokasi cache/proxy temp |
| `nginx_run_dir` | string | `/var/run` | Run dir untuk pid |
| `nginx_pid_path` | string | `/var/run/nginx.pid` | Path PID file |
| `nginx_worker_processes` | string | `auto` | Worker processes (auto = 1 per CPU core) |
| `nginx_worker_connections` | int | `1024` | Max connections per worker |
| `nginx_keepalive_timeout` | int | `65` | Keepalive timeout detik |
| `nginx_client_max_body_size` | string | `25m` | Max upload body size |
| `tls_self_signed_generate` | bool | `false` | ⚠️ LEGACY, DO NOT MODIFY. Inline managed-host generate SSL DITONGAK TOTAL sejak v0.1.0+. Generate self-signed via CLI `agra certificates generate` pre-deploy, atau set `tls_cert_path` / `tls_key_path` untuk custom CA/LetsEncrypt di /etc/agra/globals.yml. |
| `tls_self_signed_cn` | string | `{{ monitoring_vip | default(inventory_hostname) }}` | Common Name self-signed cert |
| `tls_self_signed_days_valid` | int | `3650` | Masa berlaku self-signed cert (10 tahun) |
| `tls_self_signed_country` | string | `ID` | Subject C (Country) cert |
| `tls_self_signed_state` | string | `Jakarta` | Subject ST (State) cert |
| `tls_self_signed_locality` | string | `Jakarta` | Subject L (Locality) cert |
| `tls_self_signed_organization` | string | `agra-monitoring` | Subject O (Organization) cert |
| `tls_self_signed_organizational_unit` | string | `it` | Subject OU (Organizational Unit) cert |
| `tls_cert_path` | string | `/etc/agra/ssl/agra.crt` | Path certificate (default = auto self-signed) |
| `tls_key_path` | string | `/etc/agra/ssl/agra.key` | Path private key |
| `tls_ca_path` | string | `/etc/agra/ssl/agra-ca.crt` | Path CA chain (opsional) |
| `tls_dhparam_path` | string | `/etc/agra/ssl/dhparam.pem` | Path Diffie-Hellman params |
| `tls_dhparam_bits` | int | `2048` | Panjang bit DH param (2048 = balance keamanan & waktu generate) |
| `tls_grafana_cert_path` | path | `""` | Dedicated cert Grafana HTTPS default server block (scalable per-domain). Kosong → fallback `tls_cert_path` global. |
| `tls_grafana_key_path` | path | `""` | Dedicated key Grafana. |
| `tls_prometheus_cert_path` | path | `""` | Dedicated cert Prometheus dedicated HTTPS server block. Kosong → fallback `tls_cert_path` global. |
| `tls_prometheus_key_path` | path | `""` | Dedicated key Prometheus. |
| `tls_protocols` | string | `TLSv1.2 TLSv1.3` | Protocols TLS yang diizinkan |
| `tls_ciphers` | string | *cipher suite string* | Cipher suite ECDHE-only (forward secrecy) |
| `tls_prefer_server_ciphers` | string | `on` | Prioritaskan cipher order server |
| `tls_session_timeout` | string | `1d` | Timeout SSL session cache |
| `tls_session_cache` | string | `shared:SSL:10m` | SSL session cache shared memory |
| `tls_session_tickets` | string | `off` | Disable TLS session tickets (PFS lebih baik) |
| `tls_stapling` | string | `on` | OCSP stapling |
| `tls_stapling_verify` | string | `on` | Verifikasi OCSP response |
| `tls_hsts_max_age` | string | `31536000` | HSTS max-age (1 tahun) |
| `tls_hsts_include_subdomains` | bool | `true` | HSTS includeSubDomains |
| `tls_hsts_preload` | bool | `false` | HSTS preload (false = tidak otomatis submit ke list preload) |
| `grafana_backend_url` | string | `http://127.0.0.1:{{ grafana_port | default(3000) }}` | Upstream reverse proxy Grafana (internal bind) |
| `prometheus_backend_url` | string | `http://127.0.0.1:{{ prometheus_port | default(9090) }}` | Upstream reverse proxy Prometheus (internal bind) |
| `server_name` | string | computed (grafana site) | Nginx `server_name` directive untuk site Grafana: HANYA gabungan `grafana_domain` + `monitoring_vip` (tidak include hostname/inventory_hostname node, karena hostname bukan server alias publik). Catch-all `_` hanya ditambahkan jika KEDUA value (`grafana_domain` DAN `monitoring_vip`) sama-sama kosong. |
| `nginx_http_port` | int | `80` | Port HTTP |
| `nginx_https_port` | int | `443` | Port HTTPS |
| `nginx_uid` | int | `101` | UID numeric user nginx worker di official alpine image (101) — untuk chown runtime dirs log/cache writable. |
| `nginx_gid` | int | `101` | GID numeric group nginx worker di official alpine image (101). |
| `nginx_dir_mode` | string (octal) | `"0755"` | File mode untuk log/cache runtime writable dirs (default rwxr-xr-x). Valid octal string e.g. `"0750"` untuk restrict group non-writable. |

Catatan: Untuk custom cert CA-signed, taruh `agra.crt`, `agra.key`, opsional `agra-ca.crt` di folder `/etc/agra/config/nginx/ssl/` (di control node sebelum deploy, atau remote di managed host) — config.yml akan otomatis copy ke `/etc/nginx/ssl/` tanpa overwrite self-signed generate.

## 7. Backup & Restore

| Variabel | Tipe | Default | Deskripsi |
|---|---|---|---|
| `backup_destination_type` | string | `local` | `local` \| `s3` |
| `backup_destination_path` | string | `/var/backups/agra` | Path backup lokal (di control node) |
| `backup_retention_days` | int | `14` | Retensi backup |
| `backup_include_prometheus_tsdb` | bool | `false` | Sertakan snapshot TSDB Prometheus |
| `backup_s3_enabled` | bool | `false` | Aktifkan mirror backup ke S3 |
| `backup_s3_bucket` | string | `""` | Nama bucket S3 |
| `backup_s3_endpoint` | string | `""` | Kosong = AWS S3 default; diisi untuk S3-compatible (MinIO, dll) |
| `backup_s3_region` | string | `""` | Region S3 |
| `backup_s3_access_key` | string (secret) | `""` | Ref ke `vault_backup_s3_access_key` |
| `backup_s3_secret_key` | string (secret) | `""` | Ref ke `vault_backup_s3_secret_key` |
| `enable_scheduled_backup` | bool | `false` | Aktifkan backup terjadwal |
| `backup_schedule_cron` | string | `0 2 * * *` | Jadwal cron backup otomatis |

## 8. Passwords (etc/agra/passwords.yml — WAJIB di-vault)

| Variabel | Deskripsi |
|---|---|
| `vault_grafana_admin_password` | Password admin dashboard Grafana |
| `vault_grafana_database_password` | Password koneksi database Grafana (mysql/postgresql) |
| `vault_grafana_secret_key` | Secret key signing Grafana (session, CSRF, remember cookie) |
| `vault_keepalived_auth_pass` | Auth pass VRRP keepalived |
| `vault_backup_s3_access_key` | Access key S3 untuk backup |
| `vault_backup_s3_secret_key` | Secret key S3 untuk backup |

## 9. Inventory Groups (bukan variabel, tapi bagian dari skema struktural)

| Grup | Deskripsi |
|---|---|
| `[monitoring]` | Host co-located: Grafana + Prometheus + Nginx |
| `[grafana]` | Default `:children monitoring`, bisa dioverride terpisah |
| `[prometheus]` | Default `:children monitoring`, bisa dioverride terpisah |
| `[node_exporter]` | Seluruh host yang dimonitor |

## 10. Konvensi Umum

- Semua flag boolean pakai prefix `enable_`.
- Semua variabel versi Docker WAJIB format: `<service>_image` + `<service>_tag`.
- Semua path pakai suffix `_path` (file) atau `_dir` (direktori).
- Semua secret hanya boleh direferensikan lewat prefix `vault_` dari
  `passwords.yml`, tidak pernah didefinisikan langsung di `globals.yml`.
