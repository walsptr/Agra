# Contributing Guide — Panduan Kontribusi Agra

Terima kasih berminat berkontribusi ke agra! Dokumen ini menjelaskan code of conduct, setup development environment, workflow standar, format commit, cara test lokal, dan checklist PR yang WAJIB kamu ceklis sebelum submit.

---

## Code of Conduct (Singkat 3 Paragraf)

**Paragraf 1: Inklusif & Ramah.** Kami berkomitmen menjadikan komunitas agra lingkungan yang ramah, aman, dan inklusif untuk siapa saja — tanpa memandang latar belakang, tingkat pengalaman, gender, identitas, disabilitas, atau pilihan teknologi. Berkomunikasilah dengan sopan, hargai pendapat yang berbeda, dan bantu yang baru belajar tanpa menghakimi.

**Paragraf 2: Tetap Fokus pada Teknis.** Diskusi, issue, dan PR harus fokus pada teknis, arsitektur, fitur, bug, dan kualitas kode. Tidak toleran terhadap personal attack, sarkasme, flamewar non-teknis, atau perilaku yang membuat orang lain tidak nyaman berkontribusi. Jika kamu menemukan perilaku tidak sesuai, lapor ke maintainer lewat jalur pribadi — jangan feed troll di publik.

**Paragraf 3: Kualitas & Long-term Maintainability.** Setiap kontribusi harus meninggalkan codebase dalam keadaan setidaknya SEBAIK — dan sebaiknya LEBIH BAIK — daripada saat kamu mulai. Jangan menambah technical debt yang disengaja. Jika kamu menambah fitur, tambahkan juga dokumentasi dan testnya. Jika kamu fix bug, sertakan penjelasan root cause dan cara reproduce-nya di commit message atau PR description.

---

## 1. Setup Development Environment

```bash
# 1. Clone fork/kamu atau upstream repo
git clone git@github.com:<your-username>/agra.git
cd agra

# 2. Buat virtual environment (isolasi dependensi)
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip + install requirements inti
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Ansible Core (TERPISAH dari requirements.txt)
pip install "ansible-core>=2.16"

# 5. Install package agra SECARA EDITABLE + extra dependencies DEV
#    "[dev,full]" = termasuk ansible-lint, molecule, pytest, yamllint
pip install -e ".[dev,full]"

# 6. Install Ansible Galaxy collections (jika dibutuhkan oleh role)
ansible-galaxy collection install \
  community.general \
  community.docker \
  community.mysql \
  community.postgresql \
  ansible.posix

# 7. Verifikasi setup OK
agra --help                      # → keluar daftar 9 commands
ansible-lint --version           # → ansible-lint 24+
molecule --version               # → molecule 6+
yamllint --version               # → yamllint 1+
```

Dengan ini, kamu punya:
- CLI `agra` secara editable (perubahan kode Python langsung ter-reflect tanpa install ulang)
- Linter (ansible-lint, yamllint) untuk cek kualitas
- Molecule untuk integration test per role

---

## 2. Workflow Standard (Git Branch + PR)

Ikuti workflow ini untuk SETIAP kontribusi (fitur baru, fix bug, docs update):

```bash
# Step 1: Pastikan lokal sync dengan upstream main
git checkout main
git pull upstream main    # (asumsi upstream = remote utama agra)

# Step 2: Buat branch baru dengan nama deskriptif (prefix standar)
# Format:
#   feat/<scope>-<deskripsi-singkat>    (fitur baru)
#   fix/<scope>-<deskripsi-singkat>     (perbaikan bug)
#   docs/<scope>-<deskripsi-singkat>   (perbaikan/tambah dokumentasi)
#   refactor/<scope>-<deskripsi>       (refactor kode tanpa ubah behavior)
#   chore/<scope>-<deskripsi-singkat>  (maintenance CI, dependency, dll)

# Contoh:
git checkout -b feat/roles-alertmanager-integration
# Atau:
git checkout -b fix/cli-destroy-confirm-flag-not-checked

# Step 3: Kerjakan perubahan → commit sesering mungkin (commit kecil dan fokus)
$EDITOR file-yang-diubah
git add file-yang-diubah
git commit            # (lihat §3 Conventional Commits)

# Step 4: Push branch ke fork kamu
git push origin feat/roles-alertmanager-integration

# Step 5: Buka GitHub/GitLab → Buat Pull Request dari branch kamu ke `main` upstream
#    Deskripsi PR wajib:
#    - Apa yang diubah (ringkas 1-2 paragraf)
#    - Kenapa perlu perubahan ini
#    - Cara test yang sudah kamu lakukan
#    - Checklist §5 (copy paste ke deskripsi PR, tandai - [x] yang terpenuhi)
```

Jangan pernah commit langsung ke `main`. Selalu lewat PR, selalu butuh minimal 1 approval maintainer sebelum merge (kecuali hotfix kritikal yang disetujui maintainer lead).

---

## 3. Conventional Commits — Format Commit Message

**WAJIB** pakai format [Conventional Commits](https://www.conventionalcommits.org/) untuk SETIAP commit message. Ini memudahkan auto-generate changelog dan menandai breaking changes.

Format:
```
<type>(<scope>): <subject line max 72 chars, imperative present tense, lowercase kecuali nama proper>

<optional body: penjelasan detail, wrap 80 chars>

<optional footer: BREAKING CHANGE: <penjelasan>>
```

### 5 Contoh yang Paling Sering Dipakai

```
feat(roles): tambah role alertmanager hybrid docker/native
```
→ Fitur baru di level role Ansible.

```
fix(cli): cek --yes-i-really-mean-it SEBELUM panggil ansible pada destroy
```
→ Fix bug di CLI wrapper (safety guard sebelumnya tidak jalan di edge case).

```
docs(variables): sinkronkan variabel keepalived section 5 dengan SCHEMA
```
→ Update dokumentasi variabel reference di docs/.

```
refactor(playbooks): ekstrak _health_check_post.yml jadi reusable partial
```
→ Refactor tanpa ubah behavior eksternal (tapi struktur kode lebih baik).

```
chore(ci): tambah github action ansible-lint + yamllint pada PR
```
→ Maintenance CI, dependency bump, task operasional non-fitur.

Tambahan scope yang valid: `common`, `grafana`, `prometheus`, `node_exporter`, `keepalived`, `nginx`, `backup`, `design`, `architecture`, `genpwd`, `upgrade`, `rollback`, dll (apa saja sesuai folder/module).

---

## 4. 4 Cara Test Lokal — WAJIB dijalankan SEBELUM Submit PR

### 4a. Test Idempotency (Paling Penting!)

Jalankan `agra deploy` (atau role target) **dua kali berturut-turut**, run kedua HARUS `changed=0` pada task-level (tidak ada task yang report changed).

```bash
# Setup inventory test all-in-one lokal (Vagrant/Docker-in-Docker/LXC)
# Run 1:
agra deploy -i inventory/test-allinone
# Record jumlah changed

# Run 2 KEMBALI dengan command SAMA:
agra deploy -i inventory/test-allinone
# EXPECTED: changed SEMUA task = 0 (hanya gather_facts yang gather)
```

Jika ada task yang report changed di run kedua → itu bug idempotency. Perbaiki sebelum submit (tambahkan `creates:`, `removes:`, `changed_when: false` jika command memang re-run design, atau perbaiki logic condition).

### 4b. Syntax Check + Linter

```bash
# Syntax check seluruh playbook dan role
ansible-playbook ansible/site.yml --syntax-check -i inventory/all-in-one
ansible-playbook ansible/playbooks/*.yml --syntax-check -i inventory/all-in-one

# ansible-lint — pastikan 0 error, 0 warning high-severity
ansible-lint ansible/playbooks/ ansible/roles/grafana/ ansible/roles/prometheus/

# yamllint — seluruh YAML (indent, trailing space, line length)
yamllint etc/agra/ ansible/ tests/
```

Ignore hanya jika benar-benar terpaksa, dan cantumkan komentar `# noqa: <rule>` dengan alasan jelas.

### 4c. Test CLI 9 Commands `--help` Exit 0

Semua 9 commands `agra` WAJIB support `--help` dan exit dengan code 0:

```bash
for cmd in check genpwd deploy upgrade rollback destroy backup restore tls; do
  echo "=== agra $cmd --help ==="
  agra $cmd --help > /dev/null
  echo "exit code: $?"    # EXPECTED: SEMUA 0
done
```

Opsional: test destructive command dengan `--check` mode (destroy/restore):
```bash
agra destroy --yes-i-really-mean-it --check -i inventory/all-in-one
agra restore --yes-i-really-mean-it --check -i inventory/allinone -n test-backup
```

### 4d. Molecule Test (untuk perubahan role)

Jika perubahan kamu menyentuh suatu role (misal: fix Grafana native install), jalankan molecule scenario untuk role tersebut:

```bash
# Test role grafana
cd ansible/roles/grafana
molecule test -s default     # Full lifecycle: create → prepare → converge → idempotence → verify → destroy
molecule test -s native_mode # (jika ada scenario mode native spesifik)

# Test role keepalived biasanya butuh 2 node scenario
cd ../../roles/keepalived
molecule test -s ha_2node
```

Kalau role kamu belum ada scenario molecule, **minimal** jalankan idempotency test 4a secara manual.

---

## 5. PR Checklist (Minimal 6 Item WAJIB)

Copy-paste checklist berikut ke deskripsi Pull Request kamu. **TIDAK BOLEH** ada `- [ ]` yang belum diceklis untuk issue non-trivial. Jika ada item yang tidak relevan, tulis alasan kenapa skip.

```markdown
- [ ] SCHEMA VARIABEL TERUPDATE: Setiap variabel baru yang ditambahkan di role `defaults/main.yml`
      SUDAH ditambahkan juga ke `docs/variables.md` pada commit YANG SAMA.
- [ ] IDEMPOTENCY PASS: deploy 2x berturut-turut → run kedua `changed=0` (tested di environment lokal/Vagrant/molecule).
- [ ] SAFETY GUARD 2-LAYER UNTUK OPERASI DESTRUKTIF: Jika PR menambah command destruktif baru,
      SUDAH ada validasi flag eksplisit `--yes-i-really-mean-it` di CLI (Layer 1)
      DAN `assert` di playbook level (Layer 2) sebelum perubahan benar-benar dijalankan.
- [ ] TIDAK CAMPUR LOGIC DOCKER/NATIVE DI FILE TASK YANG SAMA: Logic mode deployment
      SUDAH mengikuti Router Pattern di `tasks/main.yml` (include config.yml → docker.yml/native.yml terpisah).
      Tidak ada `when: agra_deployment_mode == 'docker'` yang tersebar di dalam `config.yml`.
- [ ] TIDAK ADA INSTALL/PROVISIONING DATABASE (MySQL/PostgreSQL): Role/task yang ditambah
      TIDAK MELAKUKAN instalasi, provisioning, setup replication, atau manajemen HA
      terhadap MySQL/MariaDB/PostgreSQL. Hanya koneksi ke database external yang sudah ada.
- [ ] DOCUMENTASI & TEST: README role di-update (jika ada perubahan perilaku),
      changelog dicantumkan, dan test case untuk fitur baru sudah ada di molecule atau
      disebutkan manual test di deskripsi PR.
- [ ] LINTER CLEAN: ansible-lint dan yamllint tidak mengeluarkan error atau warning high severity
      untuk file yang diubah.
- [ ] CONVENTIONAL COMMITS: Commit message SUDAH mengikuti format
      `type(scope): subject` (feat/fix/docs/refactor/chore) sesuai §3.
```

PR yang tidak checklist di atas akan diberi label `needs-more-work` dan diminta perbaikan sebelum di-review maintainer.

**Selamat berkontribusi** — setiap PR (bahkan typo fix di docs!) sangat kami hargai!
