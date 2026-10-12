# Role: nginx

Reverse proxy di setiap host `[monitoring]` (container `agra-nginx`, image
`nginx:1.27-alpine`). Grafana dilayani di root `/` sebagai `default_server`,
dengan atau tanpa `grafana_domain`. Prometheus hanya dipublikasikan jika
diminta. Desain: contexts/DESIGN.md §8.

- `enable_https: true` (default): 443, port 80 redirect 301 ke 443, HSTS.
  `false`: Grafana di port 80.
- Cert dibaca dari **control node** (`tls_cert_path` / `tls_key_path`, default
  hasil `agra certificates generate`) dan disalin ke `/etc/nginx/ssl/` di setiap
  host. CA chain (`tls_ca_path`) dan `dhparam.pem` disalin hanya jika ada; CA
  chain menyalakan OCSP stapling (`enable_ssl_stapling` untuk memaksa ON/OFF).
- Prometheus (tanpa auth): `prometheus_domain` → server block sendiri;
  `expose_prometheus_via_nginx: true` → path `/prometheus/` di site Grafana.
  `/api/v1/admin/*`, `/-/quit`, `/-/reload` selalu 403.
- `/healthz` hanya di `127.0.0.1:18080` (`nginx_health_port`) untuk health
  check keepalived.

## Variabel utama

| Variabel | Default | Keterangan |
|---|---|---|
| `enable_nginx` | `true` | `false` = tanpa reverse proxy; Grafana listen di `0.0.0.0:3000` |
| `enable_https` | `true` | |
| `nginx_tag` | `1.27-alpine` | |
| `nginx_http_port` / `nginx_https_port` | `80` / `443` | |
| `nginx_health_port` | `18080` | Loopback saja, tidak dibuka di firewall |
| `grafana_domain` | `""` | Bersama `monitoring_vip` menjadi `server_name` |
| `prometheus_domain` | `""` | Server block Prometheus |
| `expose_prometheus_via_nginx` | `false` | `/prometheus/` di site Grafana |
| `tls_cert_path` / `tls_key_path` | `/etc/agra/ssl/agra.crt` / `.key` | Path di control node |
| `tls_grafana_cert_path` / `tls_prometheus_cert_path` | `""` | Cert per site (kosong = `tls_cert_path`) |
| `tls_protocols` / `tls_ciphers` | `TLSv1.2 TLSv1.3` / ECDHE-only | |
| `tls_hsts_max_age` | `31536000` | |

## Contoh

Cert CA-signed (path di control node):

```yaml
tls_cert_path: /etc/agra/ssl/custom/fullchain.pem
tls_key_path: /etc/agra/ssl/custom/privkey.pem
```

lalu `agra deploy -i <inventory> --tags nginx`.

Prometheus di domain sendiri:

```yaml
prometheus_domain: prom.example.com
tls_prometheus_cert_path: /etc/agra/ssl/custom/prom-fullchain.pem
tls_prometheus_key_path: /etc/agra/ssl/custom/prom-privkey.pem
```

Ganti cert self-signed dan sebarkan: `agra tls regenerate`.

## Override (`first_found`)

- `/etc/agra/config/nginx/nginx.conf.j2`
- `/etc/agra/config/nginx/sites-available/grafana.conf.j2`
- `/etc/agra/config/nginx/sites-available/prometheus.conf.j2`
- `/etc/agra/config/nginx/conf.d/agra-healthz.conf.j2`

Mis. untuk menambah basic auth di depan Prometheus: salin
`templates/sites-available/prometheus.conf.j2` ke path override lalu ubah.
