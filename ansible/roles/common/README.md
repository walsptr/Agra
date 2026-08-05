# Role: common

Preparasi host umum untuk agra monitoring stack, dijalankan SEBELUM semua role service. Mendukung hybrid deployment mode: `docker` (instal Docker + Python SDK, buat shared network bridge) dan `native` (validasi systemd, prepare package manager). Dijalankan ke seluruh host di inventory (host monitoring dan host yang dimonitor).

## Variabel Utama

| VARIABEL | DEFAULT | DESKRIPSI |
|---|---|---|
| `common_home_dir` | `/var/lib/agra` | Base persist data directory |
| `common_etc_dir` | `/etc/agra` | Direktori config agra di managed host |
| `common_os_packages` | list (rsync, openssl, dll) | Daftar OS packages umum di-install semua host |
| `common_firewall_tool` | `auto` | Tool firewall: `auto` \| `ufw` \| `firewalld` \| `none` |
| `common_docker_network_name` | `agra_network` | Nama Docker bridge network shared antar container service |

## Contoh Penggunaan

Override di `/etc/agra/globals.yml`:
```yaml
agra_deployment_mode: native
common_firewall_tool: ufw
common_firewall_ports_tcp:
  - 8080
  - 9090
common_docker_network_name: monitoring_net
```

Atau apply role di custom playbook:
```yaml
- hosts: all
  gather_facts: true
  become: true
  roles:
    - role: common
      tags: [common]
```

Lihat contexts/DESIGN.md untuk pola router config+docker+native.
