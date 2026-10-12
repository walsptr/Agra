# Role: node_exporter

Node Exporter (metrics OS & hardware) di setiap host grup `[node_exporter]`,
sebagai container `agra-node-exporter` (`--network=host`, `--pid=host`, root
filesystem di-mount read-only). Listen di `0.0.0.0:9100`; firewall (role
`common`) hanya membuka port itu untuk node `[prometheus]`. Target Prometheus
dibuat otomatis dari grup yang sama (role `prometheus`, file_sd).

## Variabel utama

| Variabel | Default | Keterangan |
|---|---|---|
| `enable_node_exporter` | `true` | |
| `node_exporter_port` | `9100` | |
| `node_exporter_image` / `node_exporter_tag` | `prom/node-exporter` / `v1.8.2` | |
| `node_exporter_collectors_enabled` | `[]` | → `--collector.<nama>` |
| `node_exporter_collectors_disabled` | `[]` | → `--no-collector.<nama>` |
| `node_exporter_textfile_dir` | `""` | Direktori host berisi file `*.prom`; di-mount read-only dan dipakai `--collector.textfile.directory` |
| `node_exporter_log_level` | `info` | |

## Contoh

`/etc/agra/globals.yml`:

```yaml
node_exporter_collectors_enabled:
  - systemd
node_exporter_collectors_disabled:
  - mdadm
node_exporter_textfile_dir: /var/lib/node_exporter/textfile
```

Host yang hanya dimonitor masuk `[node_exporter]`, bukan `[monitoring]`:

```ini
[app]
app1 ansible_host=10.0.0.21

[node_exporter:children]
monitoring
app
```
