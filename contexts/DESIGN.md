# DESIGN.md — agra

Dokumen ini menjelaskan pola desain teknis yang harus diikuti konsisten di
seluruh role dan komponen agra. Ini adalah rujukan "bagaimana" — untuk
"apa" dan "kenapa" lihat ARCHITECTURE.md dan PRD.md.

## 1. Pola Role: Docker-only dengan shared config layer

Setiap role service (prometheus, node_exporter, grafana) WAJIB mengikuti pola
berikut — role hanya mengimplementasi docker, tidak ada native binary logic:

```
roles/<service>/
├── defaults/main.yml       # semua default value (versi, port, path, dst)
├── tasks/
│   ├── main.yml             # router: include config.yml lalu docker.yml
│   ├── validate_ha.yml      # (opsional) assert khusus HA, di-include jika relevan
│   ├── config.yml           # render config, SHARED
│   └── docker.yml           # container deployment logic
├── templates/
│   └── <service>.yml.j2     # default config template
```

`tasks/main.yml`:
```yaml
- include_tasks: validate_ha.yml
  when: enable_ha_<service> | default(false) | bool

- include_tasks: config.yml

- include_tasks: docker.yml
```

§1A. Absolute ETC_DIR Path Loading (Kolla-Ansible Pattern)
   - CLI constants.ETC_DIR = /etc/agra (absolute).
   - group_vars/all.yml menggunakan include_vars /etc/agra/globals.yml absolute.
   - SEMUA playbooks vars_files: [/etc/agra/globals.yml, /etc/agra/passwords.yml]
   - CLI util load_globals_yaml(): PRIORITAS baca /etc/agra, FALLBACK warning ke PROJECT_ROOT/etc/agra HANYA jika file tidak ada (mode legacy untuk development).

## 2. Pola Config Override (mekanisme inti "Kolla-style")

Semua render config WAJIB memeriksa custom config user lebih dulu sebelum
fallback ke template default role, menggunakan `lookup('first_found', ...)`:

```yaml
- name: Render <service> config
  template:
    src: "{{ lookup('first_found', {
        'files': [
          '/etc/agra/config/<service>/<service>.yml.j2',
          '<service>.yml.j2'
        ],
        'paths': [role_path + '/templates']
      }) }}"
    dest: /etc/<service>/<service>.yml
```

Aturan turunan:
- Custom config **menggantikan seluruh file**, bukan merge partial — supaya
  perilakunya predictable dan tidak ada "magic merge" yang membingungkan.
- Setiap service yang punya config file harus punya folder default di
  `/etc/agra/config/<service>/` (boleh kosong) sebagai dokumentasi struktur
  yang didukung.

## 3. Desain Inventory & Group Variable

```
[monitoring]              # host co-located: grafana + prometheus + nginx
[grafana:children]
monitoring
[prometheus:children]
monitoring
[node_exporter]           # semua host yang dimonitor
```

Aturan:
- Role TIDAK BOLEH mengasumsikan jumlah host tertentu — selalu gunakan
  `groups['<group>']`, `groups['<group>'] | length`, dan iterasi, bukan
  hardcode host tunggal.
- Node "master/primary" dalam grup HA selalu didefinisikan sebagai
  **host pertama dalam grup** (`groups['monitoring'][0]`) — konvensi ini
  konsisten dipakai di seluruh project (keepalived priority, backup source,
  upgrade order).
- Override manual topologi (misal pisah grafana dan prometheus ke host
  berbeda) harus tetap didukung dengan mengisi grup `[grafana]`/`[prometheus]`
  secara eksplisit tanpa `:children monitoring`.

## 4. Desain HA — Keepalived

- Satu `vrrp_instance` per grup `[monitoring]`, VIP tunggal
  (`monitoring_vip`) untuk Grafana + Prometheus + Nginx sekaligus.
- Priority: host pertama di grup mendapat priority tertinggi (MASTER default).
- `track_script` WAJIB mengecek health endpoint aplikasi (HTTP), bukan hanya
  ping/network:
  ```
  vrrp_script chk_monitoring {
      script "/usr/local/bin/agra_monitoring_healthcheck.sh"
      interval 2
      fall 3
      rise 2
      weight -20
  }
  ```
- Health check dianggap gagal jika **salah satu** dari Grafana/Prometheus
  tidak sehat (combined check, bukan independen) — filosofi: node co-located
  gagal sebagai satu unit.
- Role `keepalived` ditulis generik/reusable (parameterized service name, VIP,
  interface, script health check) supaya bisa dipakai ulang untuk kebutuhan
  VIP lain di masa depan tanpa duplikasi kode.
- Role `keepalived` HANYA di-include ketika `groups['monitoring'] | length > 1`
  — tidak ada flag eksplisit terpisah untuk mengaktifkan VIP itu sendiri.

## 5. Desain Data Grafana untuk HA

```yaml
grafana_database: sqlite   # sqlite | mysql | postgresql
enable_ha_grafana: false
```

- Jika `grafana_database: sqlite` dan `enable_ha_grafana: true`: aktifkan job
  rsync periodik dari node master (`groups['monitoring'][0]`) ke seluruh node
  standby, dijalankan via cron/systemd-timer, interval dikontrol
  `grafana_sqlite_sync_interval`.
- Jika `grafana_database: mysql/postgresql`: role grafana HANYA melakukan
  koneksi (`grafana_database_host`, port, credential) — TIDAK PERNAH
  melakukan provisioning/instalasi database. Validasi konektivitas dilakukan
  di precheck (`wait_for` ke host:port).
- `assert` wajib: `enable_ha_grafana: true` dengan `grafana_database: sqlite`
  tanpa `grafana_sqlite_sync_method` terdefinisi → gagal precheck dengan pesan
  jelas.

## 6. Desain Prometheus (tanpa flag HA)

- Role prometheus diterapkan ke seluruh `groups['prometheus']` dengan config
  identik (template sama, scrape target sama).
- Scrape target (`file_sd`) di-generate dari seluruh host di
  `groups['node_exporter']` (dan grup exporter lain di masa depan), BUKAN
  di-hardcode.
- Tidak ada logic khusus "jika lebih dari 1 node maka begini" di dalam role
  prometheus sendiri — ketahanannya murni konsekuensi topologi.

## 7. Desain Versioning & Upgrade

Variabel versi menggunakan single versioning via docker image tag:

```yaml
<service>_image: ...
<service>_tag: ...
```

Alur `agra upgrade`:
1. `agra check` (precheck, termasuk validasi versi baru jika ada version
   matrix)
2. Backup config + database (reuse mekanisme `agra backup create`)
3. Simpan versi lama ke `/etc/agra/.installed_versions.yml` di tiap host
   (untuk referensi rollback)
4. Rolling: `serial: 1`, `max_fail_percentage: 0`, urutan host = seluruh
   standby dulu, master (`groups['monitoring'][0]`) di posisi terakhir:
   ```yaml
   monitoring_upgrade_order: "{{ (groups['monitoring'][1:]) + [groups['monitoring'][0]] }}"
   ```
5. Health check per-host sebelum lanjut ke host berikutnya — kegagalan
   menghentikan proses (tidak lanjut ke host lain).

Rollback (`agra rollback --service <name>`):
- Baca versi dari `.installed_versions.yml`, deploy ulang role dengan versi
  tersebut.
- WAJIB tampilkan warning eksplisit jika target rollback berbeda major version
  dari versi saat ini (risiko inkompatibilitas format data/schema), dan
  menyarankan restore dari backup sebagai alternatif yang lebih aman.

## 8. Desain Reverse Proxy & TLS

```yaml
enable_nginx: true
enable_https: true
tls_cert_path: ""      # kosong = self-signed otomatis
tls_key_path: ""
expose_prometheus_via_nginx: false
```

- Self-signed di-generate hanya jika file belum ada (`creates:` guard) —
  idempotent, tidak regenerate setiap run.
- Custom cert (`tls_cert_path` diisi) sepenuhnya menggantikan self-signed,
  agra tidak melakukan manajemen lifecycle terhadap cert custom (di luar
  tanggung jawab agra — biasanya dikelola CA/ACME eksternal).
- Renewal self-signed: manual via `agra tls regenerate`. `agra check`
  menampilkan warning jika expiry < 30 hari (read-only check, tidak
  regenerate otomatis).

§5A. SSL Lifecycle 2 Fase (Pre-deploy Control Node + Post-deploy Managed Node)
   ┌─ PHASE 1 (PRIMARY): Pre-deploy control node via `agra certificates generate`
   │  Output: /etc/agra/ssl/agra.{crt,key,dhparam.pem} (owner root:root, key 0600, dh 0644, dir 0750)
   │  Ini sumber utama. Role nginx config task (block custom cert copy) akan menyalin dari tls_cert_path (/etc/agra/ssl/agra.crt default) ke managed host /etc/nginx/ssl.
   └─ PHASE 2 (FALLBACK): Inline managed host backward-compat generate (role nginx self-signed block creates guard)
      DIJALANKAN HANYA JIKA phase 1 cert TIDAK DITEMUKAN (user belum `agra certificates generate` atau custom path tidak valid).
      Output: nginx_config_dir/ssl/agra.*, tetap dipertahankan tanpa flag regenerate.

## 9. Desain Secrets

- Seluruh field password didefinisikan di template `passwords.yml.j2` sebagai
  daftar key kosong secara default.
- `agra genpwd`: mengisi HANYA field yang masih kosong dengan random string
  aman (idempotent — field yang sudah terisi tidak ditimpa).
- `agra genpwd --vault`: generate lalu langsung `ansible-vault encrypt`
  file-nya.
- Tidak ada secret yang boleh muncul di `globals.yml` — semua secret harus
  lewat `passwords.yml` dan direferensikan sebagai variabel (mis.
  `grafana_database_password: "{{ vault_grafana_database_password }}"`).

## 10. Desain Backup & Restore

Struktur output (lihat SCHEMA.md untuk daftar variabel lengkap):

```
<backup_destination_path>/<timestamp>/
├── manifest.yml          # versi service, tipe backup, checksum
├── grafana/
├── database/              # dump, hanya jika grafana_database mysql/postgresql
├── prometheus/
├── alertmanager/
├── agra-config/            # globals.yml, passwords.yml (tetap ter-vault)
└── certs/
```

Alur eksekusi:
1. Tentukan node master monitoring (`groups['monitoring'][0]`, atau node yang
   sedang MASTER VRRP jika terdeteksi).
2. Dump/export dilakukan di node tersebut ke staging lokal
   (`/tmp/agra-backup-staging/`).
3. `fetch` hasil staging ke **control node**, dikumpulkan ke
   `backup_destination_path/<timestamp>/`.
4. Generate `manifest.yml` + checksum.
5. Jika `backup_s3_enabled: true`: sync folder timestamp ke S3 SETELAH backup
   lokal selesai dan tervalidasi (local-first, bukan direct-to-S3).
6. Cleanup: hapus backup lokal & S3 yang lebih tua dari `backup_retention_days`.
7. Cleanup staging di node target.

`agra restore`:
- Validasi `manifest.yml` (versi service saat backup vs versi saat ini) →
  tampilkan warning jika berbeda, tidak otomatis block kecuali user tidak
  konfirmasi.
- WAJIB backup kondisi saat ini terlebih dahulu sebelum menimpa (safety
  backup-before-restore).
- WAJIB flag konfirmasi eksplisit (`--yes-i-really-mean-it`), sama seperti
  `agra destroy`.

Prometheus TSDB: default TIDAK termasuk dalam backup
(`backup_include_prometheus_tsdb: false`). Jika diaktifkan, WAJIB
menggunakan Prometheus snapshot API resmi (`/api/v1/admin/tsdb/snapshot`),
tidak boleh `tar` folder data secara langsung (risiko corrupt).

## 11. Desain Pre-flight Check (`agra check`)

Semua `assert` yang tersebar di berbagai role (jumlah node HA, backend
database, konektivitas eksternal, expiry TLS) dikumpulkan dalam satu
playbook `playbooks/precheck.yml`, dipecah per section dengan nama task yang
jelas, dan menghasilkan output ringkas per kategori (pass/fail/warning) —
bukan hanya berhenti di assert pertama yang gagal jika memungkinkan
dikumpulkan sekaligus untuk feedback lengkap ke user.

## 12. Desain Safety untuk Operasi Destruktif

- `agra destroy`: default TIDAK menghapus data (`prometheus_data_dir`,
  Grafana data). Data baru dihapus jika flag `--purge-data` eksplisit
  disertakan. Wajib flag `--yes-i-really-mean-it`.
- `agra restore`: wajib flag `--yes-i-really-mean-it`, dan otomatis membuat
  safety backup dari state saat ini sebelum menimpa.
