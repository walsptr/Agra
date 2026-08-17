# RULES.md — agra

Aturan wajib diikuti setiap kali menulis atau mengubah kode di project ini
(role, playbook, CLI wrapper). Ini bukan saran, ini konvensi yang harus
konsisten supaya project tetap maintainable saat berkembang.

## 1. Struktur Role

- Setiap role service WAJIB mengikuti pola router (`main.yml` →
  `config.yml` + `docker.yml`) sesuai DESIGN.md §1. Role hanya mengandung
  logic docker, tidak ada logic native binary.
- Setiap role WAJIB punya `defaults/main.yml` berisi seluruh variabel yang
  dipakai role tersebut dengan nilai default yang aman. Tidak boleh ada
  variabel "tak terdokumentasi" yang cuma diketahui dari isi task.
- Setiap role WAJIB punya `README.md` singkat: fungsi role, variabel utama,
  contoh penggunaan.

## 2. Konvensi Penamaan Variabel

- Prefix nama service selalu di depan: `grafana_*`, `prometheus_*`,
  `node_exporter_*`, `keepalived_*`.
- Flag boolean SELALU diawali `enable_`: `enable_grafana`, `enable_https`,
  `enable_ha_grafana`. Dilarang pakai `_enabled` sebagai suffix atau variasi
  lain agar konsisten dan predictable saat grep.
- Semua service menggunakan variabel `<service>_image` dan `<service>_tag`
  untuk menentukan versi docker image (single versioning via docker image
  tag). Tidak ada variabel terpisah untuk native package version.
- Path selalu variabel eksplisit dengan suffix `_path` atau `_dir`, tidak
  pernah di-hardcode di dalam task/template.
- Semua secret WAJIB berada di `passwords.yml`, direferensikan dengan prefix
  `vault_` di tempat pemakaiannya (mis. `vault_grafana_database_password`)
  supaya jelas asalnya dari file yang di-vault, bukan dari `globals.yml`.

## 3. Idempotency

- Setiap task WAJIB idempotent — jalankan dua kali berturut-turut harus
  menghasilkan `changed: false` pada run kedua (kecuali task yang memang
  by design selalu re-run, seperti healthcheck).
- Command/shell module HARUS pakai guard (`creates:`, `removes:`,
  `changed_when:`) — dilarang command mentah tanpa guard idempotency kecuali
  benar-benar tidak ada state yang bisa dicek.
- `agra genpwd` tidak boleh menimpa password yang sudah terisi.

## 4. Validasi & Assert

- Semua syarat HA/topologi/konektivitas (jumlah node minimal, backend
  database wajib, dsb) WAJIB dalam bentuk `assert` yang dikumpulkan di
  `playbooks/precheck.yml`, bukan tersembunyi di tengah role tanpa pesan
  error yang jelas.
- Pesan `fail_msg` WAJIB menjelaskan: apa yang salah, kenapa itu wajib, dan
  saran perbaikan singkat — bukan sekadar "assertion failed".
- Warning (bukan hard-fail) dipakai untuk kondisi yang berisiko tapi tetap
  bisa dilanjutkan atas keputusan user sadar (contoh: TLS expiry mendekati,
  rollback major version).

## 5. Config Override

- Setiap render config WAJIB memakai pola `lookup('first_found', ...)` sesuai
  DESIGN.md §2 — dilarang menulis config langsung tanpa jalur override
  custom, sekecil apapun service-nya.
- Folder `etc/agra/config/<service>/` HARUS dibuat (boleh kosong/placeholder)
  untuk setiap service baru yang ditambahkan, sebagai dokumentasi implisit
  struktur yang didukung.

## 6. Inventory & Topologi

- Role DILARANG mengasumsikan jumlah host tertentu. Selalu pakai
  `groups['<group>']`, jangan hardcode `localhost` atau nama host spesifik
  di dalam role (boleh di file inventory contoh saja).
- "Node master/primary" selalu `groups['<group>'][0]` — konvensi ini
  konsisten di seluruh project, jangan buat aturan berbeda di role lain
  tanpa alasan kuat dan didokumentasikan di DESIGN.md.

## 7. Keamanan

- Dilarang keras menyimpan secret plaintext di file mana pun selain
  `passwords.yml` sebelum di-vault, dan dilarang commit file `passwords.yml`
  yang belum ter-encrypt ke version control (harus ada `.gitignore` /
  pengingat eksplisit).
- HTTPS default aktif (`enable_https: true`) — service baru yang exposed
  HTTP harus melalui Nginx/TLS, tidak boleh expose port service langsung ke
  publik sebagai default.
- Fitur auto-failover apa pun yang melibatkan promote/demote otomatis (mis.
  pola `keepalived_auto` untuk pihak eksternal) WAJIB menyertakan fencing
  script — dilarang implementasi promote-only tanpa demote/fencing di sisi
  node yang kehilangan status aktif.
- 7.11 Private key file (*.key, *.pem tipe private) TIDAK PERNAH di-print ke stdout/stderr (hanya print PATH file). chmod key wajib 0600. Folder SSL /etc/agra/ssl wajib 0750.

## 8. Backup & Data Safety

- Operasi destruktif (`destroy`, `restore`) WAJIB flag konfirmasi eksplisit
  `--yes-i-really-mean-it`. Dilarang membuat command destruktif baru yang
  bisa jalan tanpa flag ini.
- Default operasi destruktif TIDAK menghapus data kecuali diminta eksplisit
  (`--purge-data`).
- Backup TSDB Prometheus (jika diaktifkan) WAJIB pakai snapshot API resmi,
  dilarang `tar`/copy langsung folder data yang sedang aktif ditulis.

## 9. Scope Boundary — Database

- agra DILARANG menambahkan role/task yang melakukan provisioning, instalasi,
  atau HA management terhadap MySQL/PostgreSQL. Jika ada kebutuhan seperti
  itu, itu di luar scope agra (lihat PRD.md §4 Non-Tujuan) — agra hanya
  boleh melakukan koneksi ke database eksternal yang sudah ada.

## 10. Versioning & Upgrade

- Upgrade WAJIB melalui alur rolling (`serial: 1`, standby dulu baru
  master) untuk grup `[monitoring]` bila lebih dari 1 host — dilarang
  upgrade serentak ke semua node HA sekaligus.
- Upgrade WAJIB didahului backup otomatis — dilarang membuat jalur upgrade
  yang skip backup demi kecepatan.
- Rollback lintas major version WAJIB menampilkan warning eksplisit sebelum
  eksekusi.

## 11. Testing

- Setiap role baru WAJIB punya minimal satu skenario Molecule yang menguji
  idempotency (`converge` lalu `idempotence`).
- Perubahan pada mekanisme HA/keepalived WAJIB diuji di skenario yang
  mensimulasikan minimal 2 node.

## 12. Dokumentasi

- Setiap penambahan variabel baru WAJIB langsung ditambahkan ke SCHEMA.md
  pada commit yang sama — dilarang menambah variabel tanpa update skema.
- Setiap keputusan desain baru yang mengubah/menambah pola arsitektur WAJIB
  dicatat di ARCHITECTURE.md atau DESIGN.md sebelum diimplementasikan, bukan
  didokumentasikan belakangan.

## 13. Absolute Path /etc/agra Convention (Kolla-Ansible Pattern)

13.1 Sumber kebenaran konfigurasi global SELALU di absolute path `/etc/agra/globals.yml`, `/etc/agra/passwords.yml`, `/etc/agra/config/<svc>`.
13.2 Path relative `./etc/agra` dalam repo HANYA BERISI template source untuk user copy ke `/etc/agra` saat install.
13.3 JANGAN menambah include_vars baru yang membaca dari `{{ inventory_dir }}` atau `{{ playbook_dir }}` merujuk ke etc/agra. Semua playbook baru wajib pakai absolute /etc/agra.
13.4 SSL default path wajib: `/etc/agra/ssl/agra.crt`, `/etc/agra/ssl/agra.key`. User dapat override dengan set `tls_cert_path` di globals.yml.

## 14. Single Source of Truth Konfigurasi Vars

14.1 **SATU-SATUNYA SUMBER** untuk semua variabel konfigurasi fitur & versi (fitur flag, versi service tag/image, path config, dll) adalah file **`/etc/agra/globals.yml`** di control node localhost yang di-direct-parse oleh precheck.
14.2 File **inventory** (inventory/all-in-one, inventory/multinode, custom inventory user) HANYA BOLEH berisi:
  - Daftar host dan `ansible_host` untuk koneksi SSH
  - Group membership (`[group:children]` hierarchi)
  - Variabel **koneksi** saja: `ansible_connection`, `ansible_user`, `ansible_port`, `ansible_ssh_private_key_file`, `ansible_become`, dan var koneksi SSH lainnya.
14.3 `[group:vars]` dan `host_vars/<hostname>.yml` HANYA boleh berisi **variabel koneksi group/per-host. DILARANG KERAS memasukkan vars konfigurasi fitur (monitoring_vip, enable_ha_grafana, grafana_database, grafana_tag, prometheus_tag, node_exporter_tag, enable_https, tls_*_path, dll) ke dalam inventory [group:vars] atau host_vars/* — precheck assertion TIDAK AKAN membacanya (intentional single source design), sehingga user akan mendapatkan assertion FAIL "kosong padahal sudah diset" (bukan bug, ini enforcing rule ini).
14.4 Playbook `ansible/playbooks/precheck.yml` untuk SEMUA assertion vars konfigurasi HANYA membaca via **direct parse `/etc/agra/globals.yml` python yaml.safe_load try/except** (bukan melalui `include_vars` merge namespace, bukan dari inventory hostvars, bukan dari extra_vars CLI). Mekanisme ini untuk menghindari: (a) silent fail include_vars ketika YAML syntax error atau permission file 0640, (b) scoping ambigu hostvars + delegate_to localhost run_once menyebabkan false negative non-deterministik.
14.5 Konsekuensi 14.4: Jika user upgrade dari versi agra lama (yang mengizinkan vars konfigurasi di inventory [group:vars]) dan user PINDAH TERLAMBAT (masih set vars di inventory), precheck akan FAIL dengan pesan yang user-friendly meminta user memindahkan setting tersebut ke `/etc/globals.yml`. Ini adalah expected behavior (intentional breaking change demi determinisme jangka panjang).
14.6 Pengecualian: Variabel yang *tidak di-assert* di precheck dan secara spesifik per-host (contoh niche: monitoring_vip_interface tiap node beda interface eth0 vs ens3, atau keepalived_native_package_name override distro RedHat vs Debian) — BOLEH di-set via host_vars/<hostname>.yml, KARENA tidak termasuk assertion precheck. Rule ini FOKUS ke assertion precheck vars global konfigurasi yang seharusnya seragam di semua node.
