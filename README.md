<p align="center">
  <img src="./img/logo-light.svg" alt="Agra Logo" width="300" style="max-width: 100%; height: auto;"/>
</p>

<h1 align="center">Agra - Ansible Deployment Monitoring Stack</h1>

Ansible project untuk otomasi deployment dan lifecycle management monitoring
stack: Grafana untuk dashboard, Prometheus untuk scrape + TSDB, Node Exporter
untuk metrics OS & hardware, Nginx sebagai reverse proxy TLS, dan Keepalived
untuk VIP saat multi-node.

**Docker-only** — semua komponen berjalan sebagai container (`--network=host`),
tidak ada mode native/systemd. Topologi (single node / multi-node HA) ditentukan
oleh inventory. Operasi destruktif (destroy, restore, `genpwd --force`) wajib
`--yes-i-really-mean-it`. agra tidak pernah memasang atau mengelola
MySQL/PostgreSQL — hanya connect ke database yang sudah ada.

## Install

Di **control node** (mesin tempat menjalankan `agra`), sebagai operator user (bukan sudo):

```bash
git clone https://github.com/walsptr/Agra.git
./Agra/install.sh        # butuh Python >= 3.10
```

`install.sh` membuat venv `~/.local/share/agra/venv` (atau venv yang sedang
aktif / `$AGRA_VENV`) berisi agra + ansible-core, menautkan `~/.local/bin/agra`,
dan menyiapkan `/etc/agra` (milik user Anda) dari template tanpa menimpa file
yang sudah ada. RHEL/Rocky 9: `sudo dnf install python3.12` dulu.

Tanpa checkout: `pip install <wheel/sdist agra>` di venv juga bisa — playbook
terpasang di `<venv>/share/agra/`; salin `share/agra/etc/agra/globals.yml` dan
`passwords.yml.example` ke `/etc/agra/` (`passwords.yml`, mode 0600).

Managed host: keluarga Debian/Ubuntu atau RHEL/Rocky (diuji molecule: Ubuntu
22.04 dan Rocky 9), dengan SSH + sudo dari control node. Docker Engine
dipasang oleh `agra check`.

## Quickstart

1. **Secret**:
   ```bash
   agra genpwd                        # isi /etc/agra/passwords.yml (0600)
   ```

2. **Konfigurasi** — `$EDITOR /etc/agra/globals.yml`, satu-satunya tempat var
   fitur & versi. Minimal yang perlu dicek:
   ```yaml
   monitoring_vip: ""                 # WAJIB jika [monitoring] > 1 host
   grafana_database: sqlite           # sqlite | mysql | postgresql (database eksternal yang sudah ada)
   enable_ha_grafana: false           # true = semua node Grafana memakai satu DB eksternal
   grafana_domain: ""                 # opsional
   ```

3. **Inventory** — salin `inventory/all-in-one` (1 node) atau
   `inventory/multinode` (2+ node + host yang dimonitor) dan isi host-nya.
   Inventory hanya berisi host, grup, dan var koneksi SSH (`ansible_host`,
   `ansible_user`, ...). Var konfigurasi di `[group:vars]`/`host_vars` kalah
   oleh `globals.yml`. Pengecualian: var yang memang beda per host
   (`monitoring_vip_interface`, `keepalived_unicast_ip`) di
   `host_vars/<host>.yml`, bukan di `globals.yml`.

4. **Cert self-signed** (jika `enable_https: true` dan tidak memakai cert sendiri):
   ```bash
   agra certificates generate         # /etc/agra/ssl/agra.{crt,key}
   ```

5. **Precheck** — validasi konfigurasi, lalu update paket OS + pasang Docker di node:
   ```bash
   agra check -i inventory/all-in-one
   ```

6. **Deploy**:
   ```bash
   agra deploy -i inventory/all-in-one
   ```
   Grafana di `https://<ip-node>/` (multi-node: `https://<monitoring_vip>/`),
   user `admin`, password `grafana_admin_password` di `/etc/agra/passwords.yml`.

## Command

| Command | Fungsi | Contoh |
|---|---|---|
| `agra check` | Validasi konfigurasi, lalu bootstrap node (update OS, Docker Engine). `-i` wajib. Jalankan sebelum deploy | `agra check -i inventory/multinode` |
| `agra genpwd` | Isi secret kosong di `passwords.yml`; `--force` (semua) wajib `--yes-i-really-mean-it` | `agra genpwd` |
| `agra deploy` | Deploy / reconfigure (idempotent). Tidak menjalankan precheck | `agra deploy -i inventory/all-in-one -t grafana` |
| `agra upgrade` | Precheck → backup wajib → rolling serial 1 (standby dulu, master terakhir) | `agra upgrade -i inventory/multinode --grafana-tag 11.3.0` |
| `agra rollback` | Rolling ke versi `previous` yang tercatat, atau pin `--<service>-tag` | `agra rollback -i inventory/multinode --service grafana` |
| `agra destroy` | Hapus container; data & config disimpan kecuali `--purge-*` | `agra destroy -i inventory/all-in-one --yes-i-really-mean-it` |
| `agra backup` | `create` (Grafana + opsional TSDB, disalin ke control node) / `list` | `agra backup create -i inventory/all-in-one` |
| `agra restore` | Restore dari backup di control node, dengan safety backup otomatis | `agra restore -i inventory/all-in-one -n <NAME> --yes-i-really-mean-it` |
| `agra tls` | `regenerate` cert self-signed + distribusi ke nginx / `info` | `agra tls regenerate -i inventory/multinode -y` |
| `agra certificates` | `generate` / `info` cert self-signed di control node | `agra certificates info` |

Opsi lengkap setiap command: `--help`, mis. `agra deploy --help`. `deploy`, `upgrade`,
`rollback`, `destroy`, `backup create` dan `restore` menerima opsi Ansible
umum (`-l/--limit`, `-t/--tags`, `-e`, `-v`); `-e` menimpa `globals.yml`
untuk satu run saja.

## Topologi

Ditentukan oleh grup di inventory, bukan oleh var:

| Grup | Isi |
|---|---|
| `[monitoring]` | Node yang menjalankan nginx (+ keepalived jika > 1 host). Host pertama = master: dibackup, di-upgrade terakhir, priority VRRP tertinggi |
| `[grafana]`, `[prometheus]` | Biasanya `[monitoring:children]` |
| `[node_exporter]` | Semua host yang dimonitor, termasuk node monitoring |

- **1 host di `[monitoring]`** — all-in-one, tanpa VIP.
- **2+ host** — keepalived otomatis aktif; `monitoring_vip` wajib. VIP pindah
  ke node lain jika Grafana, Prometheus, atau nginx di node pemegang VIP tidak
  sehat. Grafana di tiap node memakai SQLite sendiri, kecuali
  `enable_ha_grafana: true` (satu database MySQL/PostgreSQL eksternal untuk
  semua node). Setiap Prometheus men-scrape target yang sama secara independen.

## Konfigurasi

| File | Isi |
|---|---|
| `/etc/agra/globals.yml` | Semua var fitur & versi. Di-inject CLI sebagai extra-vars ke setiap playbook, jadi selalu menang atas inventory |
| `/etc/agra/passwords.yml` | Secret saja (0600). `agra genpwd` mengisi field kosong; kredensial S3 diisi manual |
| `host_vars/<host>.yml` (di samping inventory) | Hanya `monitoring_vip_interface` dan `keepalived_unicast_ip` |
| `/etc/agra/config/<service>/` | Override template (opsional), lihat di bawah |

Var yang paling sering diubah (default = nilai di `etc/agra/globals.yml`):

| Var | Default | Keterangan |
|---|---|---|
| `enable_grafana` / `enable_prometheus` / `enable_node_exporter` / `enable_nginx` | `true` | Matikan komponen yang tidak dipakai |
| `enable_https` | `true` | `false` = Grafana di HTTP (`nginx_http_port`) |
| `nginx_http_port` / `nginx_https_port` | `80` / `443` | |
| `<service>_tag` | lihat `globals.yml` | Versi image; ganti lewat `agra upgrade` (`--grafana-tag`, `--prometheus-tag`, `--node-exporter-tag`, atau `-e <service>_tag=...`) |
| `prometheus_retention_time` / `prometheus_retention_size` | `15d` / `""` | |
| `prometheus_domain` / `expose_prometheus_via_nginx` | `""` / `false` | Prometheus (tanpa auth) hanya keluar lewat nginx jika salah satunya diset |
| `node_exporter_port` | `9100` | Firewall hanya membukanya untuk node `[prometheus]` |
| `tls_cert_path` / `tls_key_path` | `/etc/agra/ssl/agra.{crt,key}` | Cert di control node; ganti dengan cert CA-signed jika ada |
| `backup_include_prometheus_tsdb` | `false` | Ikutkan snapshot TSDB di backup |
| `backup_retention_count` | `7` | |
| `backup_s3_enabled` | `false` | Upload backup ke S3/MinIO (`backup_s3_bucket`, `backup_s3_endpoint`, ...) |
| `common_firewall_tool` | `auto` | `ufw` \| `firewalld` \| `none` |

Komentar di `globals.yml` menjelaskan var lainnya. `agra check` memberi
warning untuk secret di `globals.yml`, var per-host di `globals.yml`, dan var
yang sudah tidak dipakai.

**Override template** — file di `/etc/agra/config/<service>/` menggantikan
seluruh template role dengan nama yang sama (tidak di-merge), mis.
`/etc/agra/config/prometheus/prometheus.yml.j2` atau
`/etc/agra/config/grafana/dashboards/*.json`. Mulai dari salinan
`ansible/roles/<service>/templates/`, lalu `agra deploy`.

## Operasi

- **Upgrade**: `agra upgrade --grafana-tag <versi>` (atau tag lain, atau ubah
  `globals.yml`). agra membuat backup dulu, lalu meng-upgrade satu host per
  kali dengan health gate: host yang hanya node_exporter, standby, master
  terakhir. Gagal di satu host = berhenti; versi current/previous dicatat di
  `/etc/agra/.installed_versions.yml` untuk `agra rollback`.
- **Backup**: Grafana (`grafana.db` lewat `sqlite3 .backup`, config,
  provisioning) dan opsional snapshot TSDB Prometheus dari master, disalin ke
  `/etc/agra/backups/` di control node dengan checksum. Database Grafana
  eksternal (MySQL/PostgreSQL) dibackup di sisi database, bukan oleh agra.
- **Restore**: dari salinan di control node, setelah verifikasi checksum dan
  safety backup kondisi saat ini.
- **Destroy**: menghapus container; data dan config tetap ada kecuali
  `--purge-data` / `--purge-config` / `--purge-all`.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,ansible]"
pytest                                   # unit, tanpa host
ruff check agra tests && yamllint . && ansible-lint
ansible-galaxy collection install -r requirements/collections.yml
cd tests && molecule test -s default     # butuh Docker
```

Skenario molecule: `default` (Ubuntu 22.04), `rocky9`, `ha-2node`, `upgrade`,
`restore`, `destroy`, `plain-http`, `minimal`. CI menjalankan semuanya.

Perubahan per versi: [CHANGELOG.md](./CHANGELOG.md).

---

# MIT License

**Copyright (c) 2025–2026 Agra Contributors**

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
