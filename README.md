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

Detail opsi: [docs/commands.md](./docs/commands.md). Dokumentasi lengkap: [docs/index.md](./docs/index.md).

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
