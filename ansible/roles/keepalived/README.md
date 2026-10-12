# Role: keepalived

VRRP virtual IP (`monitoring_vip`) untuk cluster monitoring agra multi-node,
sebagai container Docker `osixia/keepalived`. Otomatis aktif ketika
`groups['monitoring'] | length > 1` (ditentukan oleh inventory).

VIP dipegang node sehat dengan priority tertinggi. Node dianggap sehat jika
SEMUA service yang jalan di node itu menjawab 200: Grafana `/api/health`,
Prometheus `/-/healthy`, nginx `/healthz` (loopback `127.0.0.1:18080`).

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_keepalived` | computed (groups len>1) | Set `false` di globals.yml hanya untuk force-disable VIP di multi-node |
| `monitoring_vip` | `""` (WAJIB jika multi-node) | Virtual IP — akses `https://<monitoring_vip>/` |
| `monitoring_vip_interface` | interface default host | Per-host → `host_vars/<host>.yml` (globals.yml berlaku untuk semua host) |
| `keepalived_unicast_ip` | `ansible_host` | Per-host → `host_vars/<host>.yml`. IPv4 untuk VRRP unicast; wajib diset jika `ansible_host` berupa hostname/IP management |
| `keepalived_router_id` | `51` | VRRP router ID 1-255, unik per segmen L2 |
| `keepalived_priority_base` | `150` | Priority `groups['monitoring'][0]` (MASTER); -1 per posisi berikutnya |
| `keepalived_weight` | `-50` | Ditambahkan ke priority saat health check gagal; \|weight\| wajib > jumlah node - 1 |
| `keepalived_check_interval` / `_fall_count` / `_rise_count` | `2` / `3` / `2` | Health check tiap 2 detik; 3 gagal = unhealthy, 2 sukses = pulih |
| `keepalived_config_dir` | `/etc/keepalived` | conf + script di host, di-mount utuh ke container |
| `keepalived_image` / `keepalived_tag` | `osixia/keepalived:2.0.20` | Image container |

## Contoh

```ini
[monitoring]
mon1 ansible_host=10.0.0.11   ; priority 150 → MASTER
mon2 ansible_host=10.0.0.12   ; priority 149 → BACKUP
```

`/etc/agra/globals.yml`:
```yaml
monitoring_vip: "10.0.0.100"
keepalived_router_id: 52
```

`host_vars/mon1.yml` (hanya jika berbeda dari default):
```yaml
monitoring_vip_interface: ens3
keepalived_unicast_ip: 10.0.0.11
```

`keepalived_auth_pass` ada di `/etc/agra/passwords.yml` (`agra genpwd`).

## Perilaku

- Master tidak sehat (mis. Grafana mati) → setelah ~6 detik priority-nya turun
  di bawah backup sehat → VIP pindah. Master pulih → VIP kembali (preemption).
- Firewall (role `common`) membuka VRRP (protokol 112) dari node monitoring lain.
- `keepalived -t` wajib bersih sebelum container di-restart; deploy gagal jika
  keepalived tidak tetap running setelah start.
- `agra destroy` menghentikan keepalived dengan SIGTERM agar VIP dilepas.

Config override (`first_found`):
- `/etc/agra/config/keepalived/keepalived.conf.j2`
- `/etc/agra/config/keepalived/agra_monitoring_healthcheck.sh.j2`
- `/etc/agra/config/keepalived/agra_keepalived_notify.sh.j2`

Diuji oleh `tests/molecule/ha-2node` (VIP satu pemegang + failover Grafana dan
nginx bolak-balik).
