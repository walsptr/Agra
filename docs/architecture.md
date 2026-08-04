# Architecture Overview

Arsitektur agra mengadopsi filosofi Kolla-Ansible namun difokuskan pada domain monitoring stack (Grafana + Prometheus + Node Exporter), bukan OpenStack. Dokumen ini menjelaskan flow end-to-end, struktur direktori, deployment mode, topologi inventory, dan batasan scope.

Daftar command CLI lengkap: lihat [commands.md](./commands.md).

---

## 1. Gambaran Umum — Flow Eksekusi End-to-End

Flow eksekusi dari user sampai perubahan di host adalah **berlapis** dan **single entry point** (user tidak disarankan menjalankan `ansible-playbook` langsung):

```
User / Operator
   │
   │ 1. Menjalankan CLI
   ▼
agra CLI (agra/cli.py + agra/commands/*.py)
   │
   │ 2. Validasi flag safety guard,
   │    inject extra_vars, panggil ansible-runner
   ▼
Ansible Engine (ansible-playbook)
   │
   │ 3. Eksekusi playbook (ansible/playbooks/*.yml)
   │    - playbooks/precheck.yml   ← selalu jalan duluan
   │    - playbooks/deploy.yml
   │    - playbooks/upgrade_monitoring.yml
   │    - dst
   ▼
Playbook → include_role berurutan
   │
   │ 4. Urutan role sesuai topologi inventory
   ▼
Ansible Role per Service (ansible/roles/*/)
   │
   │ 5. Router pattern (main.yml → config.yml → docker|native)
   ▼
Managed Host / Target
   (Grafana, Prometheus, Node Exporter, Keepalived, Nginx berjalan di host sesuai grup inventory)
```

Prinsip topology-driven: hampir semua perilaku (HA/VIP aktif/tidak, jumlah node scrape) ditentukan dari **isi inventory**, bukan dari flag eksplisit yang harus sinkron manual.

---

## 2. Struktur Direktori

```
agra/
├── README.md                          # Entry point user + full Apache 2.0 license
├── docs/                              # Dokumentasi mendalam (folder ini)
│   ├── index.md                       # TOC + tree folder
│   ├── quickstart.md                  # Quickstart extended 8 section
│   ├── commands.md                    # Reference 9 CLI commands
│   ├── variables.md                   # Reference 157+ variabel (8 kategori)
│   ├── architecture.md                # (file ini) Gambaran arsitektur
│   ├── design.md                      # Pola desain teknis detail
│   ├── contributing.md                # Panduan kontribusi
│   ├── add-new-role.md                # Tutorial menambah role (contoh Alertmanager)
│   ├── faq.md                         # FAQ 9 Q&A
│   └── license-notice.md              # Ringkasan lisensi + attribution
├── agra/                              # Python package — CLI wrapper
│   ├── cli.py                         # Main entry point click/argparse
│   └── commands/                      # 9 module: check, genpwd, deploy, upgrade, rollback, destroy, backup, restore, tls
├── ansible/
│   ├── ansible.cfg                    # Config ansible (roles_path, dll)
│   ├── site.yml                       # Master playbook deploy penuh
│   ├── playbooks/                     # Playbook per lifecycle stage
│   │   ├── precheck.yml               # Semua assert validasi terpusat
│   │   ├── deploy.yml                 # Deploy stack
│   │   ├── upgrade_monitoring.yml     # Rolling upgrade serial:1 standby-first
│   │   ├── rollback.yml               # Rollback versi
│   │   ├── destroy.yml                # Uninstall (safety guard 2-layer)
│   │   ├── backup.yml                 # Backup on-demand
│   │   ├── restore.yml                # Restore + safety backup-before-restore
│   │   └── genpwd.yml                 # Generate password (dipanggil CLI)
│   ├── roles/                         # 6 role utama + extensible
│   │   ├── common/                    # Prep host: user, OS packages, docker, firewall, network
│   │   │   ├── defaults/main.yml
│   │   │   ├── tasks/                 # main.yml (router) + config.yml + docker.yml + native.yml
│   │   │   ├── handlers/
│   │   │   ├── templates/
│   │   │   └── README.md
│   │   ├── grafana/                   # Grafana dashboard
│   │   ├── prometheus/                # Prometheus TSDB + scraper
│   │   ├── node_exporter/             # Node Exporter OS metrics
│   │   ├── keepalived/                # Reusable VIP VRRP (otomatis jika monitoring >1 node)
│   │   └── nginx/                     # Reverse proxy + TLS
│   └── group_vars/
│       └── all.yml                    # Vars apply ke semua host
├── inventory/                         # Contoh inventory
│   ├── all-in-one                     # 1 node monitoring + node_exporter on same
│   └── multinode                      # 2+ node monitoring HA + host tambahan dimonitor
├── etc/agra/                          # Template config default untuk di-copy ke /etc/agra managed host
│   ├── globals.yml                    # Non-secret vars (157+)
│   ├── passwords.yml                  # Secret vars (plaintext chmod 0600, di .gitignore)
│   └── config/                        # Custom config override user — first_found priority
│       ├── grafana/                   # override grafana.ini.j2, dashboards/*.json
│       ├── prometheus/                # override prometheus.yml.j2
│       ├── node_exporter/             # override env file native
│       ├── keepalived/                # override keepalived.conf.j2, healthcheck script
│       └── nginx/ssl/                 # custom cert CA-signed: agra.crt, agra.key
├── tests/molecule/                    # Test per role (idempotency, HA 2-node, dst)
├── requirements.txt                   # PyYAML, dll (TIDAK termasuk ansible-core)
├── setup.py / pyproject.toml          # pip install -e . → entry point `agra`
└── .gitignore
```

Penjelasan folder kunci:
- **agra/**: Python package murni untuk CLI. Tidak ada logic Ansible disini — hanya validasi, safety guard, dan memanggil `ansible-playbook` via subprocess.
- **ansible/roles/**: Setiap role mengikuti pola router (lihat [design.md §1](./design.md)).
- **etc/agra/config/**: Folder override config user. Jika user taruh template disini, `first_found` akan mendahulukannya daripada template role (lihat [design.md §2](./design.md)).

---

## 3. Deployment Mode — Hybrid (Docker / Native)

agra mendukung **2 mode deployment global** yang dipilih via `agra_deployment_mode: docker|native` di `globals.yml`:

| Mode Docker | Mode Native |
|---|---|
| Service dijalankan sebagai Docker container via module `docker_container` | Service dijalankan sebagai binary/package + systemd unit (`agra-grafana.service`, dst) |
| Versi via `<service>_tag` (contoh: `grafana_tag: 11.2.0`) | Versi via `<service>_native_version` (contoh: `grafana_native_version: 11.2.0`) |
| Mudah upgrade: ganti tag → pull image baru | Ringan: tanpa Docker daemon overhead, cocok untuk minimal host |
| Isolasi filesystem via bind mount | Install langsung ke `/usr/local/bin/` atau package manager |

Kedua mode **share 100% logic config** (`config.yml`) — yang berbeda hanya cara install dan start service. Ini dijamin oleh **Router Pattern** di setiap role (lihat [design.md §1](./design.md)): `main.yml` include `config.yml` (SHARED) lalu conditional `docker.yml` XOR `native.yml` (ISOLATED per mode).

Penting: `agra_deployment_mode` berlaku **global** untuk seluruh service di fase ini. Override per-host/per-group adalah roadmap.

---

## 4. Topologi Inventory (All-in-One vs Multi-Node)

Prinsip **topology-driven**: perilaku deployment ditentukan murni dari isi inventory group `[monitoring]`. Role selalu berbasis `groups['monitoring']` — TIDAK PERNAH hardcode single host.

### Grup Inventory Standar

```ini
[monitoring]              # Host co-located: Grafana + Prometheus + Nginx
mon1.example.com
mon2.example.com          ; Jika >1 → OTOMATIS Keepalived VIP AKTIF

[grafana:children]        ; Default: monitoring. Bisa dioverride manual.
monitoring

[prometheus:children]     ; Default: monitoring
monitoring

[node_exporter:children]  ; Host monitoring juga dimonitor metrics-nya
monitoring

[node_exporter]           ; Host lain yang ingin dimonitor
app1.example.com
app2.example.com
db1.example.com
```

### Aturan Topologi Penting

| Kondisi | Perilaku Otomatis |
|---|---|
| `groups['monitoring'] \| length == 1` | Single node (all-in-one). Role `keepalived` → `meta: end_host` (skip, no-op idempotent). |
| `groups['monitoring'] \| length > 1` | **Multi-node HA otomatis**. Role keepalived DIJALANKAN tanpa perlu set `enable_keepalived: true`. `monitoring_vip` WAJIB diisi di globals.yml. |
| `groups['monitoring'] \| length > 1` DAN `enable_keepalived: false` | Force-disable VIP (jarang dipakai, hanya untuk kasus khusus). |

"Node master/primary" **selalu** `groups['monitoring'][0]` (host pertama di inventory). Konvensi ini dipakai konsisten:
- Keepalived priority tertinggi (MASTER VRRP)
- Source backup data Grafana sqlite
- Urutan upgrade TERAKHIR (standby dulu)

---

## 5. HA Architecture — Grafana + Keepalived + Nginx di Balik VIP

Text diagram topologi 2-node monitoring HA:

```
                           ┌─────────────────────────────────────────┐
                           │           monitoring_vip 10.0.0.100      │
                           │         (Keepalived VRRP — protocol 112) │
                           └──────────────────┬──────────────────────┘
                                              │
                 ┌────────────────────────────┴────────────────────────────┐
                 │                                                         │
    ┌────────────▼──────────────┐                              ┌───────────▼────────────────┐
    │  mon1.example.com (MASTER)│                              │ mon2.example.com (BACKUP)  │
    │  priority keepalived=201  │                              │ priority keepalived=101    │
    │  ┌─────────────────────┐  │                              │ ┌─────────────────────────┐ │
    │  │ Nginx 443/HTTPS    │  │                              │ │ Nginx 443/HTTPS         │ │
    │  │ (reverse proxy)    │  │                              │ │                         │ │
    │  └────────┬────────────┘  │                              │ └───────────┬─────────────┘ │
    │           │               │                              │             │               │
    │  ┌────────▼────┐ ┌──────▼─────┐                        │ ┌────────▼──┐ ┌────────▼──┐  │
    │  │ Grafana 3000│ │Prom 9090   │                        │ │Grafana 3000│ │Prom 9090  │  │
    │  │ (sqlite DB) │ │(TSDB dup)  │                        │ │(sqlite DB) │ │(TSDB dup) │  │
    │  └─────────────┘ └────────────┘                        │ └───────────┘ └───────────┘  │
    │                                                         │                              │
    │  grafana.db ←───── rsync cron / 5 menit ─────────────→ grafana.db (standby sync)       │
    └─────────────────────────────────────────────────────────┴──────────────────────────────┘

         Combined Health Check vrrp_script:
         HTTP GET http://127.0.0.1:3000/api/health   (Grafana)  → WAJIB 200 OK
         AND
         HTTP GET http://127.0.0.1:9090/-/healthy    (Prometheus) → WAJIB 200 OK
         KEDUANYA = 200 OK → node sehat, weight OK.
         SALAH SATU gagal → weight turun, VIP pindah ke node lain.
```

Penjelasan komponen HA:
1. **Keepalived VRRP**: 1 VIP virtual `10.0.0.100` ter-bind ke salah satu node. Protocol 112 (VRRP) harus di-allow firewall.
2. **Combined Health Check**: Node dianggap gagal SEBAGAI SATU UNIT jika Grafana ATAU Prometheus unhealthy. Tidak ada konsep "sehat separo".
3. **Nginx co-located**: Nginx aktif di SEMUA node monitoring, tapi hanya yang megang VIP yang menerima traffic user.
4. **Grafana sqlite (default)**: Sinkron via rsync periodik dari MASTER → BACKUP. Double buffer: copy ke `grafana.db.new` → `PRAGMA integrity_check` pass → backup lama ke `.bak-ts` → rename atomik.
5. **Prometheus**: Full duplication — setiap node scrape target yang sama secara independen. Tidak ada replikasi TSDB.

Jika `grafana_database: mysql/postgresql` — maka ketentuan poin 4 TIDAK BERLAKU: semua node connect ke DB external yang sama. **Tetap ingat aturan boundary: agra TIDAK PERNAH install/provisioning DB.** (lihat §7).

---

## 6. CLI Command Summary

Daftar 9 perintah `agra` (lihat [commands.md](./commands.md) untuk detail penuh Usage, Flags, Contoh, Safety Notes):

| Command | Fungsi Singkat |
|---|---|
| `agra check` | Preflight validation (read-only) |
| `agra genpwd` | Generate random passwords 14 karakter plaintext (chmod 0600) |
| `agra deploy` | Deploy/reconfigure stack (idempotent) |
| `agra upgrade` | Rolling upgrade serial:1 + backup otomatis |
| `agra rollback` | Rollback versi + warning downgrade major |
| `agra destroy` | Uninstall — safety 2-layer `--yes-i-really-mean-it` |
| `agra backup` | Backup (create/list) + snapshot TSDB API resmi |
| `agra restore` | Restore + backup-before-restore otomatis |
| `agra tls` | TLS certificate (regenerate/info/check expiry) |

---

## 7. BOUNDARY HARD RULE — Scope Batasan Proyek

⚠️ **INI ADALAH BATASAN TEGAS YANG TIDAK BOLEH DILANGGAR SIAPAPUN SAAT KONTRIBUSI:**

> agra **TIDAK PERNAH** melakukan **instalasi, provisioning, setup, atau manajemen HA** terhadap database server **MySQL / MariaDB / PostgreSQL**.
>
> Jika Grafana dikonfigurasi dengan backend `grafana_database: mysql` atau `grafana_database: postgresql`, maka **database tersebut diharapkan SUDAH ADA dan TERSEDIA** di luar ekosistem agra (on-prem, cloud managed, dikelola tim DB, dll). agra HANYA MELAKUKAN KONEKSI (validasi reachability `wait_for` host:port, inject credential connection string ke config Grafana) — TIDAK PERNAH:
> - `apt install mysql-server` / `yum install postgresql-server`
> - Membuat role/database via `mysql_user` / `postgresql_user` Ansible module
> - Setup replication (Galera, Patroni, repmgr) atau manajemen HA database
> - Backup dump database via mysqldump/pg_dump dengan tujuan provisioning
>
> Alasan: Deployment dan HA database adalah domain yang sangat kompleks sendiri, memiliki tradeoff consistency/durability/performance berbeda, dan berpotensi menjadi project tersendiri yang terpisah. Scope agra difokuskan **hanya** pada monitoring stack (visualisasi, metrics collection, alerting future).

Jika kamu menemukan Ansible task atau role dalam project ini yang mencoba melakukan hal di atas, **itu adalah bug** — laporkan dan hapus.
