# Role: prometheus

Prometheus di setiap host grup `[prometheus]`, sebagai container
`agra-prometheus`. Selalu listen di `127.0.0.1:9090` (Prometheus tanpa auth);
keluar hanya lewat nginx jika `prometheus_domain` / `expose_prometheus_via_nginx`
diset. Setiap node men-scrape target yang sama secara independen (tidak ada
flag HA, tidak ada replikasi TSDB).

- Target node_exporter dibuat dari inventory `groups['node_exporter']` ke
  `file_sd/node_exporter.yml` (`<ansible_host>:<node_exporter_port>`); perubahan
  memicu reload, bukan restart.
- `--web.enable-admin-api` selalu aktif untuk snapshot TSDB backup
  (`agra backup create --include-prometheus-tsdb`) — hanya terjangkau dari node
  itu sendiri; nginx memblok `/api/v1/admin/`.
- `prometheus.yml` divalidasi dengan `promtool` (dari image yang sama) sebelum dipakai.

## Variabel utama

| Variabel | Default | Keterangan |
|---|---|---|
| `enable_prometheus` | `true` | |
| `prometheus_port` | `9090` | |
| `prometheus_image` / `prometheus_tag` | `prom/prometheus` / `v2.53.0` | |
| `prometheus_retention_time` | `15d` | |
| `prometheus_retention_size` | `""` | mis. `50GB`; yang tercapai duluan berlaku |
| `prometheus_scrape_interval` / `prometheus_evaluation_interval` | `15s` / `15s` | |
| `prometheus_data_dir` | `/var/lib/agra/prometheus` | Tidak dihapus `agra destroy` tanpa `--purge-data` |
| `prometheus_domain` | `""` | Server block nginx sendiri |
| `expose_prometheus_via_nginx` | `false` | `/prometheus/` di site Grafana |

## Contoh

```yaml
prometheus_retention_time: 30d
prometheus_retention_size: "100GB"
prometheus_scrape_interval: 30s
```

Override penuh: `/etc/agra/config/prometheus/prometheus.yml.j2` menggantikan
template role (bukan merge) — mulai dari salinan `templates/prometheus.yml.j2`
supaya job `node_exporter` (file_sd) tetap ada.
