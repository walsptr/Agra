# Frequently Asked Questions (FAQ)

Kumpulan pertanyaan umum dan solusi singkat untuk kasus sehari-hari saat menggunakan agra.

---

## Q1: Bagaimana cara upgrade Grafana ke versi terbaru dengan cepat tanpa mengubah variabel di globals.yml?

**Jawaban:** Gunakan shortcut `--grafana-tag` pada command `agra upgrade` untuk override tag versi secara sementara di level CLI (priority tertinggi melebihi globals.yml). Contoh:

```bash
# Upgrade Grafana ke tag 11.3.0 (Docker mode)
agra upgrade -i inventory/all-in-one --grafana-tag 11.3.0

# Atau upgrade sekaligus Grafana + Prometheus
agra upgrade -i inventory/multinode \
  --grafana-tag 11.3.0 \
  --prometheus-tag v2.54.1
```

Untuk mode native, gunakan flag yang setara dengan suffix `--grafana-native-version`.

---

## Q2: Bagaimana generate SSL cert?

**Jawaban:** HANYA via 2 cara: self-signed via `agra certificates generate --include-dhparam` di control node, ATAU set variabel tls_cert_path / tls_key_path di /etc/agra/globals.yml untuk custom CA/LetsEncrypt.

---

## Q3: Saya punya sertifikat TLS CA-signed dari Let's Encrypt / Digicert / Internal CA. Bagaimana cara menggunakannya, bukan self-signed?

**Jawaban:**

1. Copy file certificate dan private key Anda ke control node di path **`/etc/agra/config/nginx/ssl/`** (folder config override tingkat tertinggi via first_found formula):

```bash
mkdir -p etc/agra/config/nginx/ssl
cp /path/to/your/fullchain.pem etc/agra/config/nginx/ssl/agra.crt
cp /path/to/your/privkey.pem etc/agra/config/nginx/ssl/agra.key
chmod 0600 etc/agra/config/nginx/ssl/agra.key
```

2. Di `etc/agra/globals.yml`, arahkan ke path cert:

```yaml
tls_cert_path: /etc/nginx/ssl/agra.crt
tls_key_path: /etc/nginx/ssl/agra.key
```

3. Re-deploy role Nginx saja dengan tag:

```bash
agra deploy -i inventory/all-in-one -t nginx --yes
```

Opsional: jika Anda juga butuh CA Chain / DHParam tambahan, taruh di folder yang sama dengan nama `ca.crt` dan `dhparam.pem` lalu set variabel `tls_ca_path` dan `tls_dhparam_path`.

---

## Q4: Ingin menambah host baru untuk monitoring node_exporter saja (misal server aplikasi / database). Apakah harus menambahkannya ke grup `monitoring`?

**Jawaban: TIDAK PERLU.** Host aplikasi/database yang hanya dipasangi node_exporter harus dimasukkan ke grup **`node_exporter`** secara terpisah, BUKAN ke grup `monitoring` (grup monitoring = tempat co-located Grafana + Prometheus + Nginx + Keepalived).

Contoh inventory:

```ini
[monitoring]
mon1 ansible_host=10.0.0.10
mon2 ansible_host=10.0.0.11

[grafana:children]
monitoring

[prometheus:children]
monitoring

# Host khusus node_exporter SAJA (tidak ada Grafana/Prometheus):
[node_exporter]
mon1 ansible_host=10.0.0.10       # jika mau co-located, masukkan juga ke grup ini
mon2 ansible_host=10.0.0.11
app1 ansible_host=10.0.0.20       # server aplikasi baru!
app2 ansible_host=10.0.0.21
db1  ansible_host=10.0.0.30       # server DB (hanya node_exporter)
```

Kemudian deploy khusus tag `node_exporter` + limit ke host baru agar cepat (tidak sentuh grup monitoring):

```bash
agra deploy -i inventory/multinode -t node_exporter -l app1,app2,db1
```

---

## Q5: Keepalived VIP tidak mau muncul / stuck di state BACKUP semua. Apa yang harus dicek urut?

**Jawaban:** Cek berurutan dari yang paling umum:

**Step 1 — Jalankan vrrp_script secara manual (combined health check):**
```bash
# Di setiap node monitoring (user root), jalankan script healthcheck:
bash /etc/keepalived/agra_monitoring_healthcheck.sh
echo "Exit code: $?"
# Expected: exit 0 (healthy). Jika exit 1 → lihat log curl mana yang gagal:
#   - Grafana /api/health tidak 200? Cek systemctl/docker grafana.
#   - Prometheus /-/healthy tidak 200? Cek systemctl/docker prometheus.
```

**Step 2 — Cek firewall VRRP protocol 112 (WAJIB bidirectional):**
```bash
# UFW (Debian/Ubuntu):
ufw allow in proto 112 from 10.0.0.0/24 comment "VRRP Keepalived"
# Firewalld (RHEL/Rocky):
firewall-cmd --add-protocol=vrrp --permanent && firewall-cmd --reload
# Pastikan kedua node (MASTER & BACKUP) bisa kirim VRRP multicast/unicast
```

**Step 3 — Cek interface VIP ada di node manapun:**
```bash
ip a | grep -A 2 "10.0.0.100"
# Jika TIDAK ADA di SATU PUN node → priority formula,
# pastikan keepalived_priority groups[0] > groups[1:]
# (default MASTER = 201, BACKUP #2 = 101, dst. turun 100 per index)
```

**Step 4 — Lihat log keepalived di /var/log/keepalived.log (atau journalctl).**

---

## Q6: Bagaimana jika saya lupa password admin Grafana / ingin reset semua password?

**Jawaban:** Jalankan `agra genpwd --force` untuk generate ulang SEMUA 6 password di `passwords.yml`. Peringatan: Ini AKAN MENIMPA passwords.yml LAMA. Password admin Grafana dan secret key Grafana AKAN BERUBAH. Setelah itu jalankan re-deploy agar credential baru terinject ke semua service.

**Tidak ada cara recover password lama jika sudah ter-overwrite.** Backup dulu file passwords.yml sebelum force jika perlu.

```bash
# ⚠️ PERINGATAN KERAS: Ini AKAN MENIMPA SEMUA password di passwords.yml LAMA.
# Sebelum force, backup dulu jika perlu:
cp etc/agra/passwords.yml etc/agra/passwords.yml.bak

# Generate ulang SEMUA password (otomatis buat backup .bak-epoch duluan)
agra genpwd --force
```

Kemudian re-deploy stack agar credential baru terinject:

```bash
agra deploy -i inventory/all-in-one
```

---

## Q7: Error "restore manifest not found" saat menjalankan `agra restore -n <nama-backup>`. Kenapa dan solusi?

**Jawaban:** Error itu terjadi karena:
1. Nama backup yang Anda panggil dengan `-n` tidak ada di daftar backup, ATAU
2. File `manifest.yml` di dalam tarball backup corrupt / hilang (manifest = catatan metadata versi service, hash integrity, list file backup).

**Solusi:**

**Cara A — Cek daftar backup resmi (recommended):**
```bash
agra backup list
# Lihat output daftar nama backup (format: agra-backup-YYYYMMDD-HHMMSS)
# Copy nama yang valid, lalu jalankan restore ulang:
agra restore -n agra-backup-20250801-153000 --yes-i-really-mean-it
```

**Cara B — Jika backup Anda berupa file tarball terpisah dari luar (migrasi / import):**
Gunakan flag `-f` dengan absolute path ke tarball.gz (manifest dibaca dari dalam tarball):

```bash
agra restore -f /home/syawal/downloads/agra-backup-exported.tar.gz --yes-i-really-mean-it
```

---

## Q8: Upgrade gagal di tengah jalan (max_fail_percentage:0 trigger abort) — sebagian node sudah upgrade, sebagian belum. Apa yang harus dilakukan?

**Jawaban:** Rolling upgrade agra sengaja didesain `serial:1` + `max_fail_percentage:0` untuk fail-fast (jika satu node gagal, seluruh playbook abort) agar tidak terjadi "split version" yang lebih luas. Berikut urutan recovery:

```bash
# Step 1: Jangan panik. MASTER node (groups['monitoring'][0]) SELALU
#         di-upgrade TERAKHIR, jadi dia masih di versi STABLE (serve VIP)
#         selama standby upgrade.

# Step 2: Analisis log error Ansible di terminal output.
#         (contoh: TLS cert expired, disk penuh di node standby, etc.)
#         Fix error di node yang gagal secara manual.

# Step 3: OPSI A — Lanjutkan upgrade jika error diperbaiki:
agra upgrade -i inventory/multinode --grafana-tag 11.3.0 --prometheus-tag v2.54.1

# Step 3: OPSI B — Jika butuh rollback ke versi SEMULA (sebelum upgrade):
agra rollback -i inventory/multinode \
  --grafana-tag 11.2.0 \
  --prometheus-tag v2.53.0 \
  --yes-i-really-mean-it
```

**Rule of thumb:** Selalu pastikan `backup create` dijalankan SEBELUM upgrade (command `agra upgrade` sebenarnya secara otomatis membuat backup sebelum eksekusi upgrade, jadi rollback selalu punya snapshot reference).

---

## Q9: Restore Prometheus TSDB corrupt / error WAL checksum failure. Apa penyebab dan solusi pencegahan?

**Jawaban:**

**Penyebab umum:**
1. Backup dilakukan DENGAN CARA `tar -cf` langsung ke folder `prometheus_data/` saat Prometheus aktif (tidak konsisten — write WAL yang belum flush ikut ter-tar dalam state setengah tulis).
2. Restore ke versi Prometheus yang JAUH berbeda (misal backup di v2.45 → restore ke v2.54 tanpa promtool check).

**Cara PENCEGAHAN (wajib selalu):**
Gunakan **Admin Snapshot API resmi** Prometheus (cara ini yang dipakai agra secara default):

```bash
# Backup DENGAN include Prometheus TSDB (default flag ini false,
# set ke true HANYA jika Anda benar-benar butuh backup TSDB full):
agra backup create --include-prometheus-tsdb
```

Command di atas menjalankan `POST /api/v1/admin/tsdb/snapshot` ke Prometheus MASTER, yang menjamin:
- Prometheus flush WAL ke disk (atomic)
- Snapshot dibuat dari state konsisten (TIDAK terjadi "setengah tulis")
- Hasil snapshot = folder read-only di `<prometheus_data_dir>/snapshots/<timestamp>/` yang kemudian di-tar oleh agra.

**Cara RECOVERY jika sudah terlanjur corrupt:**
```bash
# Step 1: Stop service Prometheus (MASTER node)
ssh mon1 systemctl stop agra-prometheus    # native
# atau
ssh mon1 docker stop agra-prometheus       # docker

# Step 2: Rename folder data corrupt ke .old (jangan langsung hapus!)
mv /var/lib/agra/prometheus /var/lib/agra/prometheus.CORRUPT-$(date +%s)
mkdir -p /var/lib/agra/prometheus && chown 65534:65534 /var/lib/agra/prometheus

# Step 3: Extract hasil snapshot resmi (dari backup.tar.gz) ke folder data.
# Step 4: Jika perlu rebuild index WAL:
cd /var/lib/agra/prometheus
promtool tsdb clean-index .    # native mode: binary promtool tersedia
# docker mode: run via temporary container mount bind.

# Step 5: Start ulang Prometheus
ssh mon1 systemctl start agra-prometheus
```
