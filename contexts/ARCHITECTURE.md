# ARCHITECTURE.md — agra

## 1. Ringkasan

**agra** adalah Ansible project untuk otomasi deployment dan lifecycle management
monitoring stack (Grafana sebagai tools utama, Prometheus + Node Exporter sebagai
tahap pertama, extensible ke exporter/agent lain di masa depan).

Filosofi desain diadopsi dari **Kolla-Ansible**, tapi fokus pada domain monitoring,
bukan OpenStack:

- Layered config: default config di-generate dari template role, bisa di-override
  penuh oleh custom config user tanpa mengubah kode role.
- Single source of truth: `globals.yml` untuk feature flag & versi, `passwords.yml`
  (ter-vault) untuk semua secret.
- CLI wrapper (`agra`) sebagai satu-satunya entry point operasional — user tidak
  disarankan menjalankan `ansible-playbook` langsung.
- Topology-driven: perilaku all-in-one vs multi-node vs HA ditentukan murni dari
  **isi inventory**, bukan dari flag terpisah yang harus disinkronkan manual.

## 2. Struktur Direktori

```
agra/
├── ansible.cfg
├── agra/                        # python package untuk CLI wrapper
│   ├── cli.py
│   ├── commands/
│   │   ├── deploy.py
│   │   ├── check.py
│   │   ├── genpwd.py
│   │   ├── upgrade.py
│   │   ├── rollback.py
│   │   ├── destroy.py
│   │   ├── backup.py
│   │   ├── restore.py
│   │   └── tls.py
├── inventory/
│   ├── all-in-one
│   └── multinode
├── etc/agra/                    # di-copy ke /etc/agra saat init
│   ├── globals.yml
│   ├── passwords.yml            # wajib di-vault sebelum dipakai di production
│   └── config/                  # custom config user, mirip kolla
│       ├── prometheus/
│       ├── grafana/
│       ├── node_exporter/
│       └── nginx/
├── ansible/
│   ├── site.yml
│   ├── playbooks/
│   │   ├── precheck.yml
│   │   ├── deploy.yml
│   │   ├── upgrade_monitoring.yml
│   │   ├── rollback.yml
│   │   ├── destroy.yml
│   │   ├── backup.yml
│   │   ├── restore.yml
│   │   └── genpwd.yml
│   ├── roles/
│   │   ├── common/               # docker/native prep, user, dir, firewall
│   │   ├── keepalived/           # reusable, dipakai untuk monitoring_vip
│   │   ├── nginx/                # reverse proxy + TLS
│   │   ├── prometheus/
│   │   ├── node_exporter/
│   │   ├── grafana/
│   │   └── alertmanager/         # roadmap
│   └── group_vars/
│       └── all.yml
└── tests/molecule/...
```

### Expected Topology Directories (Deploy-time Source)

| Path | Keterangan |
|---|---|
| `/etc/agra/globals.yml` | Absolute path deploy-time source (single source of truth). Template default di repo: `./etc/agra/globals.yml` (source copy-paste saat initialization). |
| `/etc/agra/passwords.yml` | Absolute path, wajib di-vault sebelum production. Template default di repo: `./etc/agra/passwords.yml`. |
| `/etc/agra/config/<svc>/` | Absolute path config override custom user per-service. Template struktur default di repo: `./etc/agra/config/<svc>/`. |
| `/etc/agra/ssl/agra.{crt,key,ca,dhparam.pem}` | **BARU**. Output self-signed cert pre-deploy `agra certificates generate`. Default source value tls_*_path. Dapat di-override user ke path CA-signed custom. |

## 3. Deployment Mode — Hybrid (Docker / Native)

Ditentukan oleh `agra_deployment_mode: docker | native`, default global via
`globals.yml`. Setiap role service (`prometheus`, `grafana`, `node_exporter`)
punya router task yang meng-include salah satu implementasi:

```
roles/<service>/tasks/
├── main.yml       # router
├── config.yml     # shared, dipakai kedua mode (render config, file_sd, dst)
├── docker.yml
└── native.yml
```

Fase 1: `agra_deployment_mode` berlaku **global** (satu mode untuk seluruh
deployment). Override per-host/per-group adalah roadmap fase lanjut.

**ETC_DIR Absolute Path Rule**: SELURUH ansible playbook (vars_files, include_vars group_vars/all) DAN CLI `agra` constants hanya membaca dari absolute `/etc/agra/globals.yml`, `/etc/agra/passwords.yml`, dan `/etc/agra/config/<svc>/`. Path relative `./etc/agra` HANYA BERISI template source untuk di-copy user ke `/etc/agra` saat install.

## 4. Topologi — All-in-one & Multi-node

Topologi ditentukan sepenuhnya dari **inventory**, bukan dari flag. Role ditulis
generic berbasis `groups[...]`, tidak pernah mengasumsikan single host.

Grup inti:

```
[monitoring]         # host yang menjalankan grafana + prometheus + nginx (co-located, default)
[grafana:children]    monitoring
[prometheus:children]  monitoring
[node_exporter]      # semua host yang ingin dimonitor
```

Default: Grafana dan Prometheus **co-located** di grup `[monitoring]` yang sama
(best practice project ini). User tetap bisa override manual (isi `[grafana]`
dan `[prometheus]` terpisah tanpa `:children monitoring`) bila ingin memisah.

## 5. High Availability

### 5.1 Monitoring node (Grafana + Prometheus)

- HA **tidak** berbasis flag eksplisit untuk VIP — VIP otomatis aktif ketika
  `groups['monitoring'] | length > 1`.
- Satu **`monitoring_vip`** tunggal untuk Grafana + Prometheus (co-located),
  dikelola oleh role `keepalived`.
- Health check **gabungan** (bukan per-service terpisah): kalau salah satu dari
  Grafana/Prometheus di node itu unhealthy, VIP pindah — node dianggap gagal
  sebagai satu unit.
- `enable_ha_grafana` tetap ada sebagai flag, tapi fungsinya murni untuk
  menentukan **strategi sinkronisasi data Grafana** (lihat 5.2), bukan untuk
  mengaktifkan VIP.

### 5.2 Data Grafana saat multi-node

Ditentukan oleh `grafana_database`:

| Value | Mekanisme |
|---|---|
| `sqlite` (default) | rsync periodik dari node master ke seluruh node standby |
| `mysql` / `postgresql` | **wajib** koneksi ke database eksternal (di luar scope agra) |

agra **tidak** menyediakan role untuk provisioning/HA database sendiri. Database
HA (Galera, Patroni, dsb) secara sengaja **di luar scope** project ini — akan
menjadi tools terpisah di masa depan. agra hanya melakukan *connect*, tidak
*provision*.

### 5.3 Prometheus

Prometheus **tidak punya konsep HA khusus**. Model resminya adalah *full
duplication*: setiap node di `[prometheus]` (= `[monitoring]`) scrape semua
target secara independen, storage tidak direplikasi/di-share. Menambah
ketahanan Prometheus = cukup menambah host ke inventory `[monitoring]`, tidak
ada flag `enable_ha_prometheus`.

### 5.4 Node Exporter

Tidak punya konsep HA sama sekali — dia exporter pasif. Ketahanannya otomatis
mengikuti ketahanan Prometheus yang men-scrape dia.

### 5.5 Keepalived — desain umum (reusable)

- Notify scripts (`notify_master`, `notify_backup`, `notify_fault`) dipakai
  untuk trigger aksi tambahan saat transisi state (dipakai juga sebagai basis
  auto-promote database eksternal bila relevan — di luar scope agra, tapi
  pola script-nya reusable).
- `track_script` selalu mengecek **kesehatan aplikasi** (HTTP health endpoint),
  bukan cuma ping OS/network.
- `fall`/`rise` count dipakai untuk menghindari false-positive failover akibat
  hiccup sesaat.

## 6. Reverse Proxy & TLS

- Role `nginx`, co-located di `[monitoring]`, di belakang `monitoring_vip`.
- `enable_https: true` default — self-signed certificate di-generate otomatis
  jika `tls_cert_path` kosong.
- Custom certificate (CA-signed / Let's Encrypt eksternal) didukung via
  `tls_cert_path` / `tls_key_path`.
- Prometheus UI **tidak** di-expose publik secara default
  (`expose_prometheus_via_nginx: false`) — hanya diakses internal oleh Grafana
  datasource.
- Renewal self-signed cert bersifat **manual** (`agra tls regenerate`), dengan
  peringatan expiry ditampilkan oleh `agra check`.

## 7. Versioning & Upgrade

- Versi service **fully customizable** oleh user, dipisah menurut deployment
  mode (image+tag untuk docker, package version untuk native).
- Upgrade = re-run deploy dengan versi baru (idempotent), dibungkus safety
  layer oleh CLI wrapper:
  1. Pre-flight check
  2. Backup config + database
  3. Simpan versi lama untuk referensi rollback
  4. Rolling upgrade (`serial: 1`, `max_fail_percentage: 0`), urutan **standby
     dulu, master terakhir**
  5. Health check setiap node sebelum lanjut ke node berikutnya
- Rollback tersedia (`agra rollback`), dengan warning eksplisit untuk downgrade
  major version (risiko inkompatibilitas format data TSDB/schema Grafana).

## 8. Secrets Management

- Semua password disimpan di `etc/agra/passwords.yml`, wajib di-encrypt dengan
  `ansible-vault` sebelum dipakai di production.
- `agra genpwd` men-generate password random aman untuk field yang masih
  kosong (idempotent, tidak menimpa yang sudah diisi), termasuk
  `grafana_admin_password`.

## 9. Pre-flight Check

Seluruh validasi (`assert`) yang berkaitan dengan syarat HA, jumlah node,
backend database, dsb, dikumpulkan di `playbooks/precheck.yml`, dijalankan
otomatis di awal `agra deploy`/`agra upgrade`, dan bisa dipanggil standalone
lewat `agra check`.

## 10. Backup & Restore

- Backup **local-first**, opsional di-mirror ke S3 (`backup_s3_enabled`).
- Backup dieksekusi terhadap node master monitoring, hasil di-*fetch* ke
  control node, dikumpulkan per-timestamp dalam satu folder lengkap dengan
  `manifest.yml` (metadata versi, checksum).
- Yang di-backup default: config (Prometheus, Alertmanager, Nginx/TLS),
  database Grafana (sqlite file / dump), config agra itu sendiri
  (`globals.yml`, `passwords.yml` tetap ter-vault-encrypt).
- Prometheus TSDB **tidak** di-backup by default (opt-in
  `backup_include_prometheus_tsdb`, menggunakan snapshot API resmi Prometheus).
- Retensi dikelola oleh `backup_retention_days`, dibersihkan di lokal dan S3.

## 11. Command Set CLI (`agra`)

| Command | Deskripsi | Lokasi |
|---|---|---|
| `agra check` | Jalankan seluruh pre-flight validation | `agra/commands/check.py` + `ansible/playbooks/precheck.yml` |
| `agra genpwd [--vault]` | Generate password acak, opsional langsung vault-encrypt | `agra/commands/genpwd.py` + `ansible/playbooks/genpwd.yml` |
| `agra deploy [--tags ...]` | Deploy/reconfigure | `agra/commands/deploy.py` + `ansible/playbooks/deploy.yml` |
| `agra upgrade [--tags ...]` | Rolling upgrade dengan backup & health-gate | `agra/commands/upgrade.py` + `ansible/playbooks/upgrade_monitoring.yml` |
| `agra rollback --service <name>` | Rollback ke versi sebelumnya | `agra/commands/rollback.py` + `ansible/playbooks/rollback.yml` |
| `agra destroy --yes-i-really-mean-it [--purge-data]` | Uninstall, data dipertahankan kecuali `--purge-data` | `agra/commands/destroy.py` + `ansible/playbooks/destroy.yml` |
| `agra backup create` | Backup on-demand | `agra/commands/backup.py` + `ansible/playbooks/backup.yml` |
| `agra backup list` | Lihat daftar backup | `agra/commands/backup.py` |
| `agra restore --from <timestamp> --yes-i-really-mean-it` | Restore dari backup | `agra/commands/restore.py` + `ansible/playbooks/restore.yml` |
| `agra tls regenerate [--days N]` | Regenerate self-signed certificate (inline managed node, backward compat) | `agra/commands/tls.py::cmd_regenerate` |
| `agra certificates generate [--days N] [--cn X] [--force] [--include-dhparam]` | **BARU**. Generate self-signed RSA 2048 private key + x509 cert (SAN includes localhost, 127.0.0.1, grafana_domain/monitoring_vip) di CONTROL NODE. Default output: `/etc/agra/ssl/agra.{crt,key}`. Idempotent tanpa --force. | `agra/commands/certificates.py::cmd_generate` + `ansible/playbooks/certificates.yml` (wrapper) |
| `agra certificates info [--cert-path X]` | **BARU**. Print metadata certificate issuer, CN, SAN, tanggal expiry. Warning RED jika days_remaining < 7. Exit code = 2 (critical) bila expired/kurang dari 7 hari. | `agra/commands/certificates.py::cmd_info` |

## 12. Extensibility (Roadmap)

- Exporter/agent tambahan (mysqld_exporter, blackbox_exporter, redis_exporter,
  dsb) mengikuti pola role yang sama seperti `node_exporter`.
- Alertmanager (cluster gossip built-in, dedup alert dari beberapa Prometheus).
- Long-term storage / global query (Thanos/Mimir) — di luar scope fase awal,
  dicatat sebagai extensibility point, bukan didesain variabelnya sekarang.
- Version compatibility matrix antar service (`version_matrix.yml`) — nice to
  have, bukan prioritas fase 1–2.
