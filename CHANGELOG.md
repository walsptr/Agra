# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versi
mengikuti [Semantic Versioning](https://semver.org/); selama 0.x, perubahan
yang tidak kompatibel bisa terjadi di versi minor dan selalu ditandai
**Breaking**. Versi tercatat di satu tempat: `agra/__init__.py`.

## [Unreleased]

### Diubah

- Lisensi diganti dari MIT ke Apache License 2.0 (`LICENSE`,
  `pyproject.toml`); teks lisensi tidak lagi disalin di `README.md`.
- `install.sh` menambahkan `~/.local/bin` ke PATH di `~/.bashrc` (zsh:
  `~/.zshrc`, shell lain: `~/.profile`) jika belum ada, sekali saja, lalu
  meminta `source` rc file tersebut — sebelumnya hanya WARNING untuk diedit
  manual. `AGRA_NO_MODIFY_PATH=1` mempertahankan perilaku lama.
- `agra check` kini juga memperingatkan key `globals.yml` dari layout lama
  yang selama ini diam-diam diabaikan: sinkronisasi SQLite antar node (HA
  Grafana hanya dengan database MySQL/PostgreSQL eksternal), mode native,
  dan backup terjadwal/berbasis hari.

### Diperbaiki

- Reload nginx dan Prometheus tidak lagi gagal saat container baru saja
  dibuat atau di-restart (`open() "/var/run/nginx.pid" failed`, koneksi
  ditolak): handler menunggu sampai container siap, error lain tetap
  langsung gagal.

## [0.1.0] - 2026-10-13

Rilis pertama.

### Komponen

- Grafana, Prometheus, Node Exporter, nginx (reverse proxy TLS) dan
  keepalived (VIP), semuanya container Docker dengan `--network=host`.
- Managed host: Ubuntu 22.04 dan Rocky 9 (Docker Engine: `docker.io` di
  Debian/Ubuntu, `docker-ce` di keluarga RHEL, dipasang oleh `agra check`).
- Topologi dari inventory: all-in-one, atau multi-node dengan VIP keepalived
  yang otomatis aktif saat `[monitoring]` berisi lebih dari satu host.
- Grafana memakai SQLite per node, atau satu database MySQL/PostgreSQL
  eksternal yang sudah ada (`enable_ha_grafana`). agra tidak pernah memasang
  database.

### CLI `agra`

- `check` (validasi config + bootstrap node), `genpwd`, `deploy`, `upgrade`,
  `rollback`, `destroy`, `backup create|list`, `restore`, `tls`,
  `certificates`.
- Konfigurasi hanya di `/etc/agra/globals.yml` dan secret di
  `/etc/agra/passwords.yml` (0600), di-inject sebagai extra-vars. `genpwd`
  hanya membuat secret milik agra; password database eksternal dan
  kredensial S3 diisi operator.
- `deploy` memberi warning jika versi di `globals.yml` berbeda dari versi
  terpasang (ganti versi lewat `upgrade`).
- Override template per service di `/etc/agra/config/<service>/`.
- Operasi destruktif (`destroy`, `restore`, `genpwd --force`) wajib
  `--yes-i-really-mean-it`.
- `install.sh` (bash, juga lewat `sh install.sh`) memasang agra di venv
  milik operator user dengan Python 3.10–3.14 terbaru yang ada; wheel/sdist
  membawa playbook di `<venv>/share/agra/`.

### Operasi

- Upgrade rolling satu host per kali (standby dulu, master terakhir) dengan
  backup wajib dan health gate; versi current/previous dicatat untuk
  `rollback`.
- Backup Grafana (`sqlite3 .backup`) dan snapshot TSDB Prometheus lewat Admin
  API, disalin ke control node dengan checksum, retensi, upload S3 opsional.
- Restore dari salinan di control node dengan verifikasi checksum dan safety
  backup otomatis.

### Keamanan

- Grafana dan Prometheus hanya listen di loopback di belakang nginx;
  Prometheus hanya dipublikasikan jika diminta, Admin API selalu diblok.
- Firewall (ufw/firewalld) hanya membuka port nginx dan node_exporter untuk
  node `[prometheus]`. Rule ufw berkomentar agra yang tidak lagi dibutuhkan
  (termasuk dari versi lama) dihapus saat deploy; di firewalld dilaporkan.
- Password admin Grafana di-set lewat stdin, tidak terlihat di `ps`.

### Test

- Unit test (Python 3.10–3.14), ruff, yamllint, ansible-lint.
- Molecule: `default`, `rocky9`, `ha-2node`, `upgrade`, `restore`,
  `destroy`, `plain-http`, `minimal`, dengan image ter-pin per digest.
