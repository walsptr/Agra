# PRD.md — agra (Ansible Grafana-centric Monitoring Automation)

## 1. Latar Belakang & Masalah

Deployment monitoring stack (Grafana, Prometheus, exporter) secara production-
grade — dengan dukungan multi-node, HA, config custom, dan upgrade yang aman —
umumnya dilakukan secara ad-hoc per proyek: role Ansible ditulis ulang, atau
dipasang manual satu-satu. Tidak ada standar struktur yang membuat proses ini
konsisten, repeatable, dan mudah di-maintain jangka panjang.

Kolla-Ansible sudah membuktikan pola ini bekerja baik (layered config,
CLI wrapper, versioning terkontrol) untuk domain OpenStack. Belum ada
proyek setara yang fokus pada domain **monitoring stack**.

## 2. Tujuan Produk

Membangun **agra**: Ansible project untuk deployment dan lifecycle management
monitoring stack, dengan:

- Struktur dan UX yang familiar bagi siapa pun yang pernah pakai Kolla-Ansible.
- Grafana sebagai komponen utama (pusat visualisasi), Prometheus + Node
  Exporter sebagai starting point sumber data metrics.
- Dukungan config custom per service tanpa mengubah kode role.
- Dukungan HA untuk komponen yang relevan (Grafana co-located dengan
  Prometheus di belakang VIP).
- Operasional yang aman: pre-flight check, backup otomatis sebelum upgrade,
  rollback, safety guard untuk destroy/restore.
- ✅ **Goal 7 (BARU)**: Single source of truth konfigurasi di `/etc/agra` absolute path (mengikuti pola Kolla-Ansible `/etc/kolla`), tidak lagi baca dari relative workdir `./etc/agra` saat deploy/upgrade/destroy.
- ✅ **Goal 8 (BARU)**: Workflow pre-deploy terpisah generate self-signed SSL di CONTROL NODE via command `agra certificates generate` dengan output default `/etc/agra/ssl/`, hasilnya di-copy otomatis ke managed host saat role nginx berjalan (block custom cert copy).

## 3. Target Pengguna

- Tim infrastruktur/DevOps yang butuh deploy monitoring stack berulang kali
  di banyak environment (dev/staging/prod) secara konsisten.
- Tim yang sudah familiar dengan pola Kolla-Ansible dan menginginkan UX serupa
  untuk domain monitoring.
- Tim skala kecil–menengah yang butuh HA monitoring tanpa kompleksitas penuh
  orkestrator besar (Kubernetes operator, dsb).

## 4. Non-Tujuan (Out of Scope)

- **agra tidak menyediakan provisioning atau HA management untuk database**
  (MySQL/PostgreSQL). Jika Grafana dikonfigurasi memakai database eksternal,
  database tersebut harus sudah tersedia dan dikelola di luar agra
  (termasuk HA-nya, jika ada). Ini keputusan sadar untuk memisahkan concern —
  database deployment berpotensi menjadi project terpisah di masa depan.
- Bukan orkestrator container umum (bukan pengganti Kubernetes/Nomad).
- Tidak menyediakan long-term storage/global query (Thanos/Mimir) di fase
  awal — dicatat sebagai roadmap, bukan requirement saat ini.
- Tidak menyediakan UI/dashboard manajemen sendiri — operasional murni via
  CLI (`agra`) dan Ansible.
- ❌ **Non-Goal BARU**: `agra certificates generate` HANYA untuk self-signed cert ke `/etc/agra/ssl/agra.*`. Fitur request CSR ke CA eksternal (mis. ACME LetsEncrypt, Certbot, internal CA signing) **di luar scope** — user menyediakan cert sendiri di tls_*_path jika perlu CA-signed.

## 5. Prinsip Desain

1. **Topology-driven, bukan flag-driven** — perilaku (all-in-one, multi-node,
   VIP aktif/tidak) ditentukan oleh isi inventory, seminimal mungkin flag
   eksplisit yang bisa out-of-sync dengan kondisi nyata.
2. **Config override tanpa fork kode** — custom config user selalu didahulukan
   dari default template, lewat mekanisme `first_found` di folder
   `/etc/agra/config/<service>/`.
3. **Aman secara default** — HTTPS aktif default (self-signed), backup
   otomatis sebelum operasi destruktif, safety flag wajib untuk destroy/restore.
4. **Idempotent & repeatable** — command apapun (deploy, upgrade, genpwd)
   aman dijalankan berkali-kali tanpa efek samping tak terduga.
5. **Modular & reusable** — role seperti `keepalived` didesain generik supaya
   dipakai ulang oleh service HA lain di masa depan.

## 6. Fitur & Roadmap per Fase

### Fase 1 — Fondasi
- Role `common` (prep host: docker/native, user, direktori, firewall dasar)
- Role `prometheus` (hybrid docker/native, config override, scrape target dari
  inventory)
- Role `node_exporter` (hybrid docker/native)
- Role `grafana` non-HA (hybrid docker/native, provisioning datasource +
  dashboard otomatis, database sqlite default)
- `globals.yml`, `passwords.yml` + `agra genpwd`
- CLI wrapper Python: `deploy`, `check`, `genpwd`
- Struktur `/etc/agra/config/<service>/` untuk custom config

### Fase 2 — HA & Operasional
- `enable_ha_grafana` (co-location dengan Prometheus di belakang
  `monitoring_vip`, keepalived + health check gabungan)
- Role `keepalived` (reusable)
- Sinkronisasi Grafana sqlite antar node (rsync) untuk mode HA tanpa database
  eksternal
- Dukungan `grafana_database: mysql/postgresql` (koneksi ke database
  eksternal, tanpa provisioning)
- Role `nginx` + TLS (self-signed default, custom cert override)
- `agra check` (pre-flight validation terpusat)
- `agra destroy` dengan safety guard
- Versioning custom per service + `agra upgrade` (rolling, backup otomatis,
  health-gate) + `agra rollback`
- `agra backup` / `agra restore` (local + S3)
- `agra tls regenerate`

### Fase 3 — Ekstensibilitas (belum didesain detail)
- Exporter/agent tambahan (mysqld_exporter, blackbox_exporter, dst) mengikuti
  pola role node_exporter
- Alertmanager (termasuk cluster mode untuk dedup alert bila Prometheus di
  banyak node)
- Version compatibility matrix
- Long-term storage / global query (Thanos/Mimir) — evaluasi kebutuhan lebih
  lanjut sebelum didesain

## 7. Kriteria Sukses

- Deployment all-in-one maupun multi-node bisa dilakukan hanya dengan
  mengubah file inventory, tanpa mengubah kode role.
- Custom config service bisa di-override user tanpa fork/edit role.
- Upgrade versi service tidak menyebabkan downtime pada topologi HA (rolling,
  standby dulu baru master).
- Tidak ada secret yang pernah tersimpan dalam bentuk plaintext di luar
  proses generate awal (langsung ter-vault).
- Operasi destruktif (destroy, restore) tidak bisa terjadi tanpa konfirmasi
  eksplisit.

## 8. Asumsi & Batasan

- User familiar dasar Ansible (inventory, group_vars, vault).
- Untuk `grafana_database: mysql/postgresql`, ketersediaan dan HA database
  sepenuhnya tanggung jawab user/infrastruktur eksternal.
- Self-signed TLS cukup untuk kebutuhan internal; production publik disarankan
  memakai `tls_cert_path` custom (CA-signed).
