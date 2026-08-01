# Role: keepalived

High-Availability Virtual IP (VRRP v2) untuk cluster monitoring agra multi-node. Otomatis aktif ketika `groups['monitoring'] | length > 1` (topology-driven, ARCHITECTURE §5.1). Gunakan combined health check — BOTH Grafana AND Prometheus harus sehat (200 OK), kalau salah satu fail → VIP pindah ke node standby. Mendukung hybrid mode: native package keepalived (default) atau Docker container `osixia/keepalived`.

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `enable_keepalived` | computed (groups len>1) | Auto-calculated. Normalnya TIDAK PERLU di-set manual; set `false` di globals.yml untuk force-disable VIP meskipun multi-node |
| `monitoring_vip` | `""` (WAJIB ISI jika multi-node) | Virtual IP address tunggal untuk Grafana+Prometheus+Nginx — semua user akses `https://<monitoring_vip>/grafana` |
| `monitoring_vip_interface` | `ansible_default_ipv4.interface` → fallback `eth0` | Interface jaringan fisik untuk bind VIP (eth0, ens3, enp0s3, dst) |
| `keepalived_router_id` | `51` | VRRP virtual router ID 0-255 (HARUS UNIK antar VRRP cluster di segmen L2 yang sama) |
| `keepalived_vrrp_instance` | `VI_MONITORING_01` | Nama instance VRRP di config |
| `keepalived_priority` | computed formula 201-idx*100 | Host `groups['monitoring'][0]` (pertama di inventory) = priority 201 = MASTER SELALU (deterministik) |
| `keepalived_check_interval` | `2` | Interval detik health check gabungan Grafana+Prometheus |
| `keepalived_fall_count` | `3` | Jumlah gagal berturut sebelum node dianggap unhealthy → VIP pindah |
| `keepalived_rise_count` | `2` | Jumlah sukses berturut sebelum node dianggap sehat kembali |
| `keepalived_weight` | `-20` | Pengurangan priority bila track_script fail |
| `keepalived_image` / `keepalived_tag` | `osixia/keepalived:2.0.20` | Docker image (mode docker) |

## Contoh Penggunaan

Inventory multi-node contoh (2 node monitoring + 1 app node dimonitor):
```ini
[monitoring]
mon1.example.com   ; MASTER keepalived (priority 201, idx=0)
mon2.example.com   ; BACKUP keepalived (priority 101, idx=1)

[node_exporter:children]
monitoring

[node_exporter]
app1.example.com
```

Override `group_vars/monitoring.yml` ATAU `globals.yml` untuk setup VIP HA:
```yaml
monitoring_vip: "10.0.0.100"
monitoring_vip_interface: "ens3"
keepalived_router_id: 52
enable_ha_grafana: true
grafana_database: sqlite
```

**Combined Health Check (DESIGN.md §4)**:
- `http://127.0.0.1:3000/api/health` (Grafana) HARUS 200 OK
- `http://127.0.0.1:9090/-/healthy` (Prometheus) HARUS 200 OK
- Keduanya harus pass dalam `keepalived_rise_count` berturut → node sehat
- Salah satu gagal `keepalived_fall_count` berturut → node unhealthy, VIP pindah

Config override:
- `/etc/agra/config/keepalived/keepalived.conf.j2` — override full keepalived.conf
- `/etc/agra/config/keepalived/agra_monitoring_healthcheck.sh.j2` — custom healthcheck script
- Hooks: `/etc/agra/config/keepalived/post-{master,backup,fault}.sh` (opsional, executable) dijalankan ketika state VRRP berubah.

Lihat contexts/DESIGN.md untuk pola router config+docker+native.
