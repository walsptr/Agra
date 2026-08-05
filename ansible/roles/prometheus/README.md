# Role: prometheus

Deploy Prometheus monitoring server (TSDB + scraper engine) dengan hybrid deployment mode: Docker container atau native binary install dari tarball release resmi. Termasuk config override via first_found pattern, scrape target auto-generate dari inventory `groups['node_exporter']` via file_sd, dan Admin API selalu aktif untuk snapshot TSDB backup resmi.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_prometheus` | `true` | Set `false` untuk skip deployment Prometheus |
| `prometheus_port` | `9090` | Port listen HTTP UI/API (bind ke 127.0.0.1 jika nginx aktif tanpa expose) |
| `prometheus_retention_time` | `15d` | Retensi TSDB berbasis waktu — `15d`, `6h`, `1y`, dst |
| `prometheus_retention_size` | `""` | Opsional retensi berbasis size: mis. `"50GB"` (lebih dulu terpenuhi yang mana) |
| `prometheus_scrape_interval` | `15s` | Global default scrape interval |
| `prometheus_evaluation_interval` | `15s` | Evaluasi recording/alerting rules |
| `prometheus_data_dir` | `/var/lib/agra/prometheus` | Path persist TSDB (tidak di-purge destroy default) |
| `prometheus_tag` | `v2.53.0` | Docker image tag (mode docker) |
| `prometheus_native_version` | `2.53.0` | Versi binary (mode native) |
| `expose_prometheus_via_nginx` | `false` | Expose UI publik di `/prometheus/`. Default `false` = return 403 (Prometheus default tanpa auth!) |

## Contoh Penggunaan

Override `/etc/agra/globals.yml` untuk retention 30 hari + expose UI + custom versi:
```yaml
prometheus_retention_time: 30d
prometheus_retention_size: "100GB"
prometheus_tag: v2.54.1
expose_prometheus_via_nginx: true
prometheus_scrape_interval: 30s
```

Scrape target auto-generate dari inventory:
```ini
[node_exporter]
mon1.example.com      # akan masuk file_sd sebagai target http://mon1:9100/metrics
app1.example.com
```

Custom config override: taruh template `prometheus.yml.j2` di `/etc/agra/config/prometheus/prometheus.yml.j2` — 100% menggantikan default (DESIGN.md §2, bukan partial merge).

PENTING: `--web.enable-admin-api` SELALU aktif di kedua mode agar endpoint `/api/v1/admin/tsdb/snapshot` tersedia untuk backup TSDB resmi.

Lihat contexts/DESIGN.md untuk pola router config+docker+native.
