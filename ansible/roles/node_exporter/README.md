# Role: node_exporter

Deploy Prometheus Node Exporter untuk export OS & hardware metrics (CPU, memory, disk, network, filesystem) ke endpoint HTTP yang di-scrape Prometheus. Docker container deployment. Dijalankan ke SEMUA host di grup `[node_exporter]`.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_node_exporter` | `true` | Set `false` untuk skip deployment Node Exporter |
| `node_exporter_port` | `9100` | Port listen HTTP metrics endpoint `/metrics` |
| `node_exporter_tag` | `v1.8.2` | Docker image tag |
| `node_exporter_collectors_enabled` | `[]` | Collector tambahan: `['systemd','interrupts','tcpstat']` |
| `node_exporter_collectors_disabled` | `[]` | Collector default yang dimatikan: `['arp','mdadm']` |
| `node_exporter_textfile_dir` | `""` | Path custom textfile collector (opsional, `_key="*.prom"`) |
| `node_exporter_log_level` | `info` | Log level: `debug` \| `info` \| `warn` \| `error` |

## Contoh Penggunaan

Inventory contoh (tambahkan semua host yang ingin dimonitor):
```ini
[node_exporter]
mon1.example.com
mon2.example.com
app1.example.com
db1.example.com
```

Override `/etc/agra/globals.yml` untuk enable collector systemd + disable arp:
```yaml
node_exporter_collectors_enabled:
  - systemd
node_exporter_collectors_disabled:
  - arp
  - mdadm
```

Override config custom: taruh `node_exporter.default.j2` di `/etc/agra/config/node_exporter/` (DESIGN.md §2 first_found pattern) untuk mengganti env file.

Lihat contexts/DESIGN.md untuk pola router config+docker.
