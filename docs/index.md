# Dokumentasi Agra

Pintu masuk utama dokumentasi agra: Ansible Monitoring Stack Deployment (Grafana + Prometheus + Node Exporter hybrid docker/native).

## Table of Contents

1. [Quickstart (Extended 8 Sections) — 0-7](./quickstart.md)
2. [Command Reference (9 Commands) — check, genpwd, deploy, upgrade, rollback, destroy, backup, restore, tls](./commands.md)
3. [Variables Reference (157+ variabel, 8 kategori)](./variables.md)
4. [Architecture Overview — Struktur direktori, deployment mode, topologi inventory, HA VIP](./architecture.md)
5. [Design Patterns — Router pattern, first_found, combined health check, rolling upgrade, backup snapshot API](./design.md)
6. [Contributing Guide — Setup dev env, workflow, conventional commits, testing, PR checklist](./contributing.md)
7. [Menambah Role Baru — Contoh Alertmanager 12 Step by Step](./add-new-role.md)
8. [Frequently Asked Questions (FAQ) — 9 Q&A umum](./faq.md)
9. [License Notice — Apache 2.0 ringkasan + third party attribution](./license-notice.md)

---

## Struktur Folder Proyek Agra

```
agra/
├── README.md                 # Entry point user: install, quickstart 5 langkah, command table
├── docs/                     # FOLDER INI — Dokumentasi mendalam
│   ├── index.md              # (file ini) TOC + tree folder
│   ├── quickstart.md         # Quickstart extended 8 section (0-7)
│   ├── commands.md           # Reference 9 CLI commands (H2 per command)
│   ├── variables.md          # Reference 157+ variabel (8 kategori table)
│   ├── architecture.md       # Gambaran arsitektur + boundary rules
│   ├── design.md             # Pola desain teknis role + upgrade + backup
│   ├── contributing.md       # Panduan kontribusi + PR checklist
│   ├── add-new-role.md       # Tutorial menambah role baru (contoh: Alertmanager)
│   ├── faq.md                # 9 FAQ Q&A operasional
│   └── license-notice.md     # Ringkasan lisensi + third party attribution
├── agra/                     # Python package CLI wrapper
│   ├── cli.py
│   └── commands/             # 9 module command
├── ansible/
│   ├── site.yml
│   ├── playbooks/            # precheck, deploy, upgrade, rollback, destroy, backup, restore, genpwd
│   ├── roles/                # common, grafana, prometheus, node_exporter, keepalived, nginx
│   │   ├── <role>/
│   │   │   ├── defaults/main.yml
│   │   │   ├── tasks/        # main.yml (router) + config.yml + docker.yml + native.yml
│   │   │   ├── templates/
│   │   │   ├── handlers/
│   │   │   └── README.md
│   └── group_vars/
├── inventory/                # Contoh: all-in-one, multinode
├── etc/agra/                 # Template config default
│   ├── globals.yml           # Non-secret vars (157+ variabel)
│   ├── passwords.yml         # Secret vars (wajib di-vault)
│   └── config/               # Override custom user per service
│       ├── grafana/
│       ├── prometheus/
│       ├── node_exporter/
│       ├── keepalived/
│       └── nginx/ssl/
└── tests/molecule/           # Test per role
```

---

## Navigasi Cepat

| Topik | File |
|---|---|
| Pertama kali pakai? | Mulai dari **[Quickstart](./quickstart.md)** |
| Perlu daftar perintah CLI? | Buka **[Commands](./commands.md)** |
| Ingin tau semua variabel konfigurasi? | Buka **[Variables](./variables.md)** (157+) |
| Ingin paham struktur dan topologi? | Buka **[Architecture](./architecture.md)** |
| Ingin kontribusi kode? | Mulai dari **[Contributing](./contributing.md)** |
| Ingin tambah role/service baru? | Ikuti **[Add New Role Guide](./add-new-role.md)** |
| Ada masalah operasional? | Cek **[FAQ](./faq.md)** dulu |
| Tentang lisensi dan attribution? | Buka **[License Notice](./license-notice.md)** |

Full license text Apache 2.0 ada di **[../README.md](../README.md)** bagian paling akhir.
