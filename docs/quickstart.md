# Quickstart Agra — Extended 8 Sections

Panduan setup lengkap dari nol sampai monitoring stack aktif.

---

## 0. Prasyarat

Sebelum memulai, pastikan di **control node** (laptop/VM tempat menjalankan `agra`) sudah tersedia:

| Komponen | Minimum Version | Keterangan |
|---|---|---|
| Python | 3.10+ | Perlu `venv` + `pip` |
| Ansible Core | 2.16+ | Install via pip (tidak termasuk requirements.txt) |
| Git | — | Clone repo |
| SSH Access | — | Ke semua managed host (passwordless SSH key disarankan) |
| Managed Host OS | Ubuntu 22.04+, RHEL 9+, Debian 12+ | target deployment |

Minimum resource untuk **all-in-one single node** (dev/staging):
- 2 vCPU, 4GB RAM, 40GB disk (Prometheus TSDB retention 15d ≈ 5-15GB)

Production HA 2 node:
- Tiap node: 4 vCPU, 8GB RAM, 100GB SSD
- Network: L2 segment yang sama untuk VRRP Keepalived (protocol 112 harus di-allow firewall)

---

## 1. Setup Environment (venv + Install CLI)

```bash
# 1. Clone repo
git clone https://github.com/example/agra.git && cd agra

# 2. Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies utama
pip install --upgrade pip
pip install -r requirements.txt          # PyYAML >= 6.0, requests, dll
pip install ansible-core>=2.16          # Ansible engine

# 4. Install package agra secara editable → command `agra` langsung tersedia di PATH
pip install -e .

# 5. Verifikasi — pastikan command terdeteksi
which agra        # → /<path>/agra/.venv/bin/agra
agra --help       # → keluar daftar 9 command
```

(Opsional, untuk memudahkan tanpa `source .venv` setiap kali):
```bash
# Symlink agra ke /usr/local/bin (butuh sudo, hanya jika ingin global)
# sudo ln -sf $(pwd)/.venv/bin/agra /usr/local/bin/agra
```

---

## 2. Init Config (globals.yml)

**Step 2A: Review dan edit `/etc/agra/globals.yml`** — file ini adalah single source of truth untuk semua feature flag, versi service, dan path:
```bash
$EDITOR /etc/agra/globals.yml
```

3 variabel wajib perhatikan:
```yaml
# Aktifkan fitur sinkronisasi data Grafana multi-node
# (tidak mengaktifkan VIP — VIP otomatis dari inventory len > 1)
enable_ha_grafana: false          # false | true

# Virtual IP address untuk HA 2+ node
# WAJIB diisi jika enable_ha_grafana: true ATAU inventory monitoring > 1 host
monitoring_vip: 10.0.0.100
```

---

## 3. GenPwd — Generate Password Random

`agra genpwd` mengisi field kosong di `/etc/agra/passwords.yml` dengan random string aman (14 chars, URL-safe). **Idempotent** — field yang sudah terisi TIDAK ditimpa kecuali pakai `--force`. File passwords.yml disimpan dalam plaintext dengan chmod 0600 (hanya owner bisa baca) dan SUDAH termasuk di dalam `.gitignore`.

```bash
# Generate password 14 karakter (plaintext, chmod 0600)
agra genpwd

# Verifikasi file isi field:
cat /etc/agra/passwords.yml
# Keluar 6 field:
#   grafana_admin_password
#   grafana_database_password
#   grafana_secret_key
#   keepalived_auth_pass
#   backup_s3_access_key
#   backup_s3_secret_key
```

Opsi lain:
```bash
# Re-generate SEMUA password (overwrite existing)
agra genpwd --force
```

> ⚠️ **PRODUKSI**: File `passwords.yml` disimpan plaintext. Lindungi dengan `chmod 0600` (sudah otomatis di-set oleh `agra genpwd`). JANGAN PERNAH commit file ini ke git (sudah di `.gitignore`). Jika butuh enkripsi, gunakan tool external seperti git-crypt, blackbox, atau sops.

---

## 4. Pilih Inventory (All-in-One / MultiNode HA)

### 4A. All-in-One (Single Node, Dev/Staging)

Gunakan `inventory/all-in-one` — semua service (grafana + prometheus + nginx + node_exporter) berjalan di 1 host yang sama:

```ini
# inventory/all-in-one
[monitoring]
mon1.example.com  ansible_host=10.0.0.10 ansible_user=ubuntu ansible_become=true

[node_exporter:children]
monitoring
```

Penjelasan grup:
- `[monitoring]` = host yang menjalankan Grafana + Prometheus + Nginx (co-located)
- `[node_exporter:children] monitoring` = otomatis host monitoring juga di-scrape metrics-nya sendiri

### 4B. MultiNode HA (2+ Node Production)

Gunakan `inventory/multinode` — minimal 2 node di grup `[monitoring]` untuk otomatis aktifkan Keepalived VIP:

```ini
# inventory/multinode
[monitoring]
mon1.example.com  ansible_host=10.0.0.11 ansible_user=ubuntu ansible_become=true
mon2.example.com  ansible_host=10.0.0.12 ansible_user=ubuntu ansible_become=true

[grafana:children]
monitoring

[prometheus:children]
monitoring

[node_exporter:children]
monitoring

# Host lain yang ingin dimonitor (bukan monitoring node)
[node_exporter]
app1.example.com  ansible_host=10.0.0.21 ansible_user=ubuntu ansible_become=true
app2.example.com  ansible_host=10.0.0.22 ansible_user=ubuntu ansible_become=true
db1.example.com   ansible_host=10.0.0.31 ansible_user=ubuntu ansible_become=true
```

Kondisi ini (2 host di `[monitoring]`) **otomatis** menyebabkan:
- Role `keepalived` aktif (tidak perlu set `enable_keepalived: true`)
- VIP `monitoring_vip` (contoh: `10.0.0.100`) ter-bind ke `mon1` (MASTER, priority 201) dan `mon2` BACKUP (priority 101)
- Combined health check: Grafana `/api/health` + Prometheus `/-/healthy` keduanya harus 200 OK

Edit `inventory/multinode`:
```bash
cp inventory/multinode inventory/multinode-prod
$EDITOR inventory/multinode-prod
```

Test koneksi SSH ke semua host:
```bash
ansible -i inventory/multinode-prod all -m ping -o
# Semua host → SUCCESS
```

---

## 4A. Pre-generate SSL Self-Signed (Opsional tapi Disarankan)

Jika `enable_https: true` (default) dan kamu TIDAK pakai custom cert CA-signed, disarankan pre-generate SSL di **control node** SEBELUM deploy agar cert konsisten disimpan di `/etc/agra/ssl/` dan tidak generate acak per managed host:

```bash
# Buat folder SSL (butuh sudo karena /etc system-wide)
sudo mkdir -p /etc/agra/ssl && sudo chmod 0750 /etc/agra/ssl

# Generate cert RSA2048 + x509 self-signed + opsional DH param (untuk DHE forward secrecy)
agra certificates generate --include-dhparam
# Output: /etc/agra/ssl/agra.crt, /etc/agra/ssl/agra.key, (opsional) /etc/agra/ssl/dhparam.pem
```

Cek info cert yang baru digenerate:
```bash
agra certificates info
```

---

## 5. Precheck — Validasi Sebelum Deploy

**Selalu jalankan `agra check` SEBELUM deploy/upgrade.** Validasi ini read-only, tidak modifikasi host apa pun:

```bash
# All-in-One
agra check -i inventory/all-in-one

# MultiNode HA — verbose untuk melihat detail
agra check -i inventory/multinode-prod -v
```

Yang divalidasi (list tidak lengkap):
- ✅ Konektivitas Ansible ke semua host (ping + become)
- ✅ `monitoring_vip` terisi jika `groups['monitoring'] | length > 1`
- ✅ Jika `grafana_database: mysql/postgresql` → `wait_for` ke host:port reachable
- ✅ TLS self-signed expiry ≥ 30 hari (warning jika < 30)
- ✅ `passwords.yml` permissions 0600 dan field terisi (warning jika masih kosong)
- ✅ Jumlah node monitoring untuk HA ≥ 2
- ✅ OS package manager siap (apt/yum/dnf cache update)
- ✅ Ruang disk cukup untuk TSDB Prometheus

Jika ada `FAILED` → perbaiki dulu sebelum lanjut ke step 6. `WARNING` boleh dilanjutkan dengan risiko sendiri.

---

## 6. Deploy Monitoring Stack

```bash
# All-in-One
agra deploy -i inventory/all-in-one

# MultiNode HA — dengan tag spesifik (opsional)
agra deploy -i inventory/multinode-prod -t grafana,prometheus,nginx
```

Alur internal playbook deploy:
1. Play `precheck.yml` → validasi ulang (bisa skip dengan `--no-precheck`, TIDAK DISARANKAN)
2. Role `common` ke SEMUA host → install OS packages, deployer install via root become, docker (jika mode docker), firewall dasar, shared network; grafana HA sync via SSH root public-key auth
3. Role `node_exporter` ke `groups['node_exporter']` → deploy exporter
4. Role `keepalived` ke `groups['monitoring']` (hanya jika len > 1) → setup VIP
5. Role `prometheus` ke `groups['prometheus']` → deploy TSDB + config scrape target
6. Role `grafana` ke `groups['grafana']` → deploy Grafana + provisioning datasource Prometheus
7. Role `nginx` ke `groups['monitoring']` → reverse proxy + TLS self-signed
8. Health check setiap service → output summary

Waktu deploy tipikal:
- All-in-One: 5-10 menit (tergantung kecepatan internet pull image docker)
- MultiNode 2 node: 10-20 menit (rolling serial:1)

---

## 7. Post Deploy Check

**Step 7A: Verifikasi endpoint sehat**

Single-node (akses langsung ke host):
```bash
# Nginx health check (HTTPS self-signed → -k untuk skip verify)
curl -k https://10.0.0.10/healthz
# → expected: "OK" atau "healthy"

# Grafana UI
curl -k https://10.0.0.10/grafana/api/health
# → expected: {"database":"ok","version":"11.2.0",...}

# Prometheus internal (di host)
# mon1$ curl -s http://127.0.0.1:9090/-/healthy
# → Prometheus is Healthy.
```

HA (akses via VIP `10.0.0.100`):
```bash
curl -k https://10.0.0.100/grafana/api/health
# → database ok
```

**Step 7B: Login Grafana dashboard**

1. Buka browser ke `https://<IP>/grafana` (single) atau `https://<VIP>/grafana` (HA)
2. Username: `admin`
3. Password: lihat field `grafana_admin_password` di `passwords.yml`:
   ```bash
   cat /etc/agra/passwords.yml | grep grafana_admin_password
   ```
4. Default datasource **Prometheus (UID: prometheus-main)** sudah tersambung otomatis
5. Cek **Explore → Metrics browser** → ketik `node_cpu_seconds_total` → Run query → harus ada data dari semua host `[node_exporter]`

**Step 7C: Cek keepalived status (jika HA)**

```bash
# Di MASTER node (mon1):
mon1$ ip a show eth0   # interface sesuai monitoring_vip_interface
# → ada secondary IP 10.0.0.100/32

# Test failover manual: matikan keepalived di MASTER
mon1$ sudo systemctl stop keepalived          # mode native
# ATAU  mon1$ docker stop agra-keepalived     # mode docker

# Cek VIP pindah ke BACKUP
mon2$ ip a show eth0
# → 10.0.0.100 sekarang di mon2

# Hidupkan kembali
mon1$ sudo systemctl start keepalived
```

**Step 7D: Test backup on-demand**

```bash
agra backup create -i inventory/all-in-one
# Output: backup disimpan ke /var/backups/agra/<timestamp>/ + manifest.yml

agra backup list
# → table daftar backup
```

Selesai! Monitoring stack production-grade sudah berjalan 🎉
