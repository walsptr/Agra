# Role: common

Dijalankan pertama ke **semua** host di inventory (host monitoring dan host
yang dimonitor). Docker Engine sendiri dipasang oleh `agra check`; role ini
memastikan `docker.service` berjalan, memasang paket OS dasar, dan mengatur
firewall per host. Container memakai `--network=host` — tidak
ada Docker network khusus; network `agra_network` peninggalan agra lama
dihapus selama masih kosong (dipakai container lain → warning saja).

Firewall (ufw/firewalld, terdeteksi otomatis) hanya membuka:

| Port | Dari | Host |
|---|---|---|
| 22/tcp | mana saja | semua |
| 80/tcp, 443/tcp (jika `enable_https`) | mana saja | `[monitoring]`, jika `enable_nginx` |
| `grafana_port` | mana saja | `[grafana]`, hanya jika `enable_nginx: false` |
| `node_exporter_port` | node `[prometheus]` | `[node_exporter]` |
| VRRP (IP proto 112) | node `[monitoring]` lain | `[monitoring]`, jika > 1 host |
| `grafana_alerting_ha_port` tcp+udp | node `[grafana]` lain | `[grafana]`, jika `enable_ha_grafana` |
| `common_firewall_ports_tcp` | mana saja | semua |

Prometheus (9090) tidak pernah dibuka.

Aturan yang tidak lagi diperlukan host itu (dibuka agra versi lama, port
yang berubah, peer yang keluar dari inventory) dihapus **hanya di ufw** dan
hanya jika masih membawa komentar yang ditulis agra (`'agra monitoring port
N'`, `'agra node_exporter scrape'`, `'agra grafana alerting HA'`); rule port SSH
tidak pernah dihapus. Rule firewalld tidak punya penanda pemilik, jadi
port yang dulu dibuka agra (80, 443, 3000, 9090) hanya dilaporkan sebagai
warning beserta perintah penghapusannya.

## Variabel utama

| Variabel | Default | Keterangan |
|---|---|---|
| `common_firewall_tool` | `auto` | `auto` \| `ufw` \| `firewalld` \| `none` |
| `common_firewall_ports_tcp` | `[]` | Port TCP tambahan, dibuka dari mana saja |
| `common_os_packages` | per OS family | Paket dasar (curl, cron, ...) |
| `common_home_dir` | `/var/lib/agra` | |
| `common_docker_service_name` | `docker` | |

## Contoh

`/etc/agra/globals.yml`:

```yaml
common_firewall_tool: firewalld
common_firewall_ports_tcp:
  - 8443
```
