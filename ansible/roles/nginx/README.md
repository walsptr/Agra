# Role: nginx

Deploy Nginx sebagai reverse proxy frontend untuk Grafana (path `/` atau `/grafana/`) dan optional Prometheus (path `/prometheus/`). Default pakai native OS package install (lebih stabil untuk reverse proxy production), tapi juga support Docker. Termasuk TLS/HTTPS self-signed auto-generate (default aktif — DESIGN.md §8) dengan Diffie-Hellman params hardening dan HSTS.

**HTTPS**: Disarankan pre-generate cert control node via `agra certificates generate --include-dhparam` sebelum deploy. Secara default cert dibaca dari `/etc/agra/ssl/agra.crt` (sesuai default `tls_cert_path` di `/etc/agra/globals.yml`). Untuk regenerate inline managed host post-deploy (emergency): `agra tls regenerate`.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_nginx` | `true` | Set `false` untuk skip deployment Nginx (service langsung expose port — TIDAK DISARANKAN production) |
| `enable_https` | `true` | Aktifkan HTTPS port 443; HTTP 80 redirect permanen 301 ke HTTPS |
| `nginx_tag` | `1.27-alpine` | Docker image tag (hanya jika mode docker; default nginx pakai native) |
| `expose_prometheus_via_nginx` | `false` | Expose Prometheus UI di `/prometheus/`. Default `false` = return 403 (Prometheus default TANPA auth) |
| `tls_self_signed_generate` | `true` | Auto-generate self-signed cert jika custom cert tidak ada (creates guard — idempotent) |
| `tls_self_signed_cn` | computed | Common Name cert: `monitoring_vip` atau `inventory_hostname` |
| `tls_self_signed_days_valid` | `3650` | Masa berlaku self-signed cert (10 tahun default) |
| `nginx_http_port` | `80` | Port HTTP listener |
| `nginx_https_port` | `443` | Port HTTPS listener |
| `grafana_backend_url` | `http://127.0.0.1:3000` | Upstream reverse proxy internal ke Grafana |
| `prometheus_backend_url` | `http://127.0.0.1:9090` | Upstream reverse proxy internal ke Prometheus |
| `tls_protocols` | `TLSv1.2 TLSv1.3` | Protokol TLS yang diizinkan (TLS 1.0/1.1 disable default) |

## Contoh Penggunaan

Skenario 1: Default all-in-one dengan self-signed HTTPS. Tidak perlu ubah apa-apa. Akses `https://<host>/grafana` — browser warning self-signed expected.

Skenario 2: Pakai custom CA-signed certificate (Let's Encrypt, internal CA, dsb):
```yaml
enable_https: true
# Taruh file di control node sblm deploy, atau copy manual ke managed host:
#   /etc/agra/config/nginx/ssl/agra.crt  (fullchain)
#   /etc/agra/config/nginx/ssl/agra.key  (privkey)
# Atau override path explicit:
# tls_cert_path: /etc/letsencrypt/live/mon.example.com/fullchain.pem
# tls_key_path:  /etc/letsencrypt/live/mon.example.com/privkey.pem
tls_ciphers: "ECDHE+AESGCM:!aNULL"
tls_hsts_preload: true
```

Skenario 3: Expose Prometheus UI (perlindungan extra: tambah basic auth di override template sendiri):
```yaml
expose_prometheus_via_nginx: true
```

Config override:
- `/etc/agra/config/nginx/nginx.conf.j2` — override global nginx.conf
- `/etc/agra/config/nginx/sites-available/agra-monitoring.conf.j2` — override site config

Untuk regenerate self-signed cert paksa: `agra tls regenerate`.

Lihat contexts/DESIGN.md untuk pola router config+docker+native.
