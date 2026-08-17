# Tutorial: Menambah Role Service Baru (Contoh: Alertmanager)

Dokumen ini memandu kamu langkah demi langkah menambahkan role service BARU ke agra, menggunakan **Alertmanager** (alerting layer untuk Prometheus) sebagai contoh. **Setiap Step WAJIB diikuti — tidak boleh skip**, terutama yang terkait safety guard, naming convention, dan pembaruan dokumentasi.

**Referensi wajib sebelum mulai:**
- Pola router design: [design.md §1](./design.md)
- Naming convention: [variables.md konvensi penamaan](./variables.md)
- Scope boundary (JANGAN install MySQL/PostgreSQL): [architecture.md §7](./architecture.md)
- Contributing workflow & PR checklist: [contributing.md](./contributing.md)

---

## Step 1: Struktur Folder Role (WAJIB Sesuai Router Pattern)

Buat struktur direktori role **persis** seperti ini. Jangan ada file tambahan yang tidak perlu di level atas (kecuali file yang ada dibawah ini).

```bash
# Dari root agra project:
mkdir -p ansible/roles/alertmanager/{defaults,handlers,tasks,templates,meta,tests}

# Buat placeholder file (nanti kita isi satu per satu)
touch ansible/roles/alertmanager/defaults/main.yml
touch ansible/roles/alertmanager/handlers/main.yml
touch ansible/roles/alertmanager/tasks/{main,validate_ha,config,docker}.yml
touch ansible/roles/alertmanager/templates/{alertmanager.yml.j2,alertmanager.env.j2}
touch ansible/roles/alertmanager/README.md
touch ansible/roles/alertmanager/meta/main.yml
```

Hasil akhir:
```
ansible/roles/alertmanager/
├── defaults/main.yml          # SEMUA variabel default + naming convention
├── handlers/main.yml          # Handler restart container
├── tasks/
│   ├── main.yml               # ROUTER HANYA: assert → include config → docker
│   ├── validate_ha.yml        # (opsional) assert khusus HA cluster Alertmanager
│   ├── config.yml             # SHARED: render config, mkdir, chown
│   └── docker.yml             # DEPLOY DOCKER: container image, mount, port
├── templates/
│   ├── alertmanager.yml.j2        # config template (dipakai first_found)
│   └── alertmanager.env.j2      # env file (opsional)
├── meta/main.yml              # dependency role (mis: butuh common)
└── README.md                  # dokumentasi role untuk user
```

Folder `tests/` untuk molecule test — dibuat Step 11.

---

## Step 2: `tasks/main.yml` — ROUTER HANYA (TIDAK BOLEH ADA TASK LAIN)

`tasks/main.yml` HANYA BERISI: (1) assert validasi 3-komponen, (2) meta end_host jika enable=false, (3) include config.yml → include docker.yml.

```yaml
---
# ansible/roles/alertmanager/tasks/main.yml
# INI ADALAH ROUTER SAJA. DILARANG menaruh task render/install disini.

# 2A. Assert 3-komponen validasi dasar
- name: "Alertmanager: validate required vars"
  assert:
    that:
      - enable_alertmanager is defined
      - alertmanager_data_dir is defined
      - alertmanager_port is defined
    fail_msg: >-
      Role alertmanager butuh variabel dasar enable_alertmanager,
      alertmanager_data_dir, alertmanager_port.
      Jika menggunakan mysql/postgresql untuk apapun di role ini,
      INGAT KEMBALI: agra TIDAK BOLEH install/provisioning DB.

# 2B. Skip seluruh role jika enable=false (idempotent no-op)
- meta: end_host
  when: not (enable_alertmanager | default(false) | bool)

# 2C. (Opsional) Validasi khusus untuk cluster HA Alertmanager
- include_tasks: validate_ha.yml
  when: enable_ha_alertmanager | default(false) | bool

# 2D. SHARED CONFIG — semua deployment Docker (WAJIB ADA, SEBELUM docker-specific)
- include_tasks: config.yml

# 2E. DOCKER DEPLOYMENT
- include_tasks: docker.yml
```

Poin penting Step 2:
- TIDAK ADA task `template:`, `file:`, `docker_container:` atau task operasional lainnya di `main.yml` — itu semua harus di `config.yml`/`docker.yml`.
- `meta: end_host` menjamin TIDAK ADA satupun task yang jalan jika `enable_alertmanager=false` (bahkan `gather_facts` untuk role ini pun tidak jalan).

---

## Step 3: `defaults/main.yml` — NAMING CONVENTION WAJIB

Daftarkan SEMUA variabel yang dipakai role ini beserta default aman. **WAJIB IKUTI naming convention (lihat variables.md intro):**

```yaml
---
# ansible/roles/alertmanager/defaults/main.yml
# NAMING CONVENTION — WAJIB IKUTI:
#  - Flag boolean: PREFIX enable_*  (contoh: enable_alertmanager)
#  - Versi docker: SUFFIX _tag       (contoh: alertmanager_tag)
#  - Path direktori: SUFFIX _dir     (contoh: alertmanager_data_dir)
#  - Path file: SUFFIX _path         (contoh: alertmanager_config_path)

# --- Flag enable ---
enable_alertmanager: true
enable_ha_alertmanager: false     # cluster gossip mode (opsional)

# --- Versi & deploy ---
alertmanager_port: 9093
alertmanager_image: prom/alertmanager
alertmanager_tag: "v0.27.0"

# --- Path (WAJIB ada suffix _dir/_path, JANGAN hardcode di task file) ---
alertmanager_data_dir: /var/lib/agra/alertmanager    # persist data (silences, notifications log)
alertmanager_config_dir: /etc/alertmanager            # config files
alertmanager_config_path: "{{ alertmanager_config_dir }}/alertmanager.yml"

# --- Peran lain ---
alertmanager_container_name: "agra-alertmanager"
alertmanager_native_binary_path: /usr/local/bin/alertmanager
alertmanager_web_listen_address: "0.0.0.0:{{ alertmanager_port }}"
alertmanager_cluster_port: 9094
alertmanager_log_level: info
# dst... (sesuaikan dengan semua variabel yang dipakai task config/docker)
```

Pengecekan Step 3:
- ✅ Flag boolean: `enable_*` prefix? (YA: `enable_alertmanager`, `enable_ha_alertmanager`)
- ✅ Semua path punya `_dir` / `_path` suffix? (YA)
- ✅ Tidak ada secret plaintext disini? (YA — secret kalau ada masuk `passwords.yml` sebagai plaintext, tidak perlu prefix. Pastikan passwords.yml sudah di .gitignore + chmod 0600)

---

## Step 4: `tasks/config.yml` — SHARED Config Render first_found

`config.yml` dipakai bersama Docker deployment. Isinya: (1) mkdir + chown/chmod untuk direktori, (2) render config WAJIB pakai lookup `first_found` formula (lihat [design.md §2](./design.md)), (3) `notify: restart alertmanager` ke handler.

```yaml
---
# ansible/roles/alertmanager/tasks/config.yml
# SHARED CONFIG untuk Docker deployment. DILARANG ada conditional mode-specific disini.

# 4A. Pastikan direktori ada — ownership UID 65534 (nobody) untuk security, sesuai role lain
- name: "Alertmanager: create data + config dirs"
  file:
    path: "{{ item }}"
    state: directory
    owner: "65534"
    group: "65534"
    mode: "0750"
    recurse: false
  loop:
    - "{{ alertmanager_data_dir }}"
    - "{{ alertmanager_config_dir }}"

# 4B. Render config dengan first_found FORMULA WAJIB.
# JIKA KAMU HAPUS lookup('first_found') disini, DESIGN VIOLATION.
- name: "Alertmanager: render alertmanager.yml"
  template:
    src: "{{ lookup('first_found', am_config_templates) }}"
    dest: "{{ alertmanager_config_path }}"
    owner: "65534"
    group: "65534"
    mode: "0640"
  notify: "restart alertmanager"
  vars:
    am_config_templates:
      files:
        # User override TERTINGGI: taruh template disini untuk custom 100%
        - "/etc/agra/config/alertmanager/alertmanager.yml.j2"
        - "/etc/agra/config/alertmanager/custom.yml.j2"
        # Default role template (TERENDAH priority)
        - "alertmanager.yml.j2"
      paths:
        - "{{ role_path }}/templates"
```

Jangan lupa: buat folder placeholder override config untuk user (di Step 12 nanti kita verifikasi):
```bash
mkdir -p etc/agra/config/alertmanager
touch etc/agra/config/alertmanager/.gitkeep
```

---

## Step 5: `tasks/docker.yml` — ISOLASI DOCKER (JANGAN ada native logic)

Isi HANYA docker-specific. Jangan ada task yang menginstall binary systemd disini.

```yaml
---
# ansible/roles/alertmanager/tasks/docker.yml
# ISOLASI DOCKER. DILARANG mencampur systemd/native command disini.

- name: "Alertmanager docker: ensure container running"
  docker_container:
    name: "{{ alertmanager_container_name }}"
    image: "{{ alertmanager_image }}:{{ alertmanager_tag }}"
    state: started
    restart_policy: unless-stopped
    network_mode: "{{ common_docker_network_name | default('bridge') }}"
    user: "65534:65534"
    ports:
      - "{{ alertmanager_web_listen_address }}:{{ alertmanager_port }}"
      - "127.0.0.1:{{ alertmanager_cluster_port }}:9094"
    volumes:
      - "{{ alertmanager_config_dir }}:/etc/alertmanager:ro"
      - "{{ alertmanager_data_dir }}:/alertmanager:rw"
    command: >
      --config.file=/etc/alertmanager/alertmanager.yml
      --storage.path=/alertmanager
      --web.listen-address=:9093
      --log.level={{ alertmanager_log_level }}
  notify: "restart alertmanager"
```

Handler untuk docker didefinisikan di Step 7.

---

## Step 6: (DITAMBAHKAN — Docker-only sekarang)

Sekarang agra **hanya mendukung Docker deployment**, jadi tidak ada `tasks/native.yml`. Semua service dijalankan sebagai container. Step docker.yml (Step 5) adalah satu-satunya mode-specific yang dibutuhkan.

---

## Step 7: `handlers/main.yml` — Restart Container Docker

Handler cukup satu task untuk restart container Docker.

```yaml
---
# ansible/roles/alertmanager/handlers/main.yml

- name: "restart alertmanager"
  docker_container:
    name: "{{ alertmanager_container_name }}"
    state: started
    restart: true
```

---

## Step 8: Update `site.yml` / `deploy.yml` — include_role dengan kondisi `when`

Edit playbook master agar role Alertmanager di-include ketika enable.

```yaml
# ansible/site.yml (potongan role urutan)
---
- name: "Deploy monitoring stack"
  hosts:
    - grafana
    - prometheus
    - node_exporter
    - alertmanager          # <<< TAMBAH GRUP INI di inventory (mis: children dari monitoring, atau grup sendiri)
  gather_facts: true
  become: true
  roles:
    - role: common
      tags: [common]
    - role: node_exporter
      tags: [node_exporter]
      when: enable_node_exporter | default(true) | bool
    - role: prometheus
      tags: [prometheus]
      when: enable_prometheus | default(true) | bool
    # >>> TAMBAH DISINI:
    - role: alertmanager
      tags: [alertmanager]
      when: enable_alertmanager | default(true) | bool
    # <<< END TAMBAH
    - role: grafana
      tags: [grafana]
      when: enable_grafana | default(true) | bool
    - role: keepalived
      tags: [keepalived, ha]
      when:
        - groups['monitoring'] | default([]) | length > 1
        - (enable_keepalived | default(true)) | bool
    - role: nginx
      tags: [nginx, tls]
      when: enable_nginx | default(true) | bool
```

Jangan lupa playbook lain seperti `upgrade_monitoring.yml`, `backup.yml` jika perlu sertakan role alertmanager didalamnya.

---

## Step 9: WAJIB UPDATE `docs/variables.md` — SAME COMMIT

Ini adalah **aturan terpenting nomor 1 dari contributing**: **setiap variabel baru yang kamu tambah di `defaults/main.yml` pada step 3 WAJIB ditambahkan ke `docs/variables.md` PADA COMMIT YANG SAMA.**

Ini adalah RULES §12 di project agra — tidak boleh ada variabel tak terdokumentasi.

Cara update:
1. Buka `docs/variables.md`
2. Tambahkan **Section 9. Alertmanager** (atau nama role baru)
3. Buat TABLE 4 KOLOM: `| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |`
4. Masukkan SEMUA variabel dari step 3 beserta default dan deskripsinya satu per satu.
5. Commit file `ansible/roles/alertmanager/defaults/main.yml` BERSAMA file `docs/variables.md` DALAM SATU COMMIT YANG SAMA — jangan pisahkan commit.

Contoh table yang harus ditambah:
```markdown
## 9. Alertmanager

| NAMA VARIABEL | TIPE | DEFAULT VALUE | DESKRIPSI |
|---|---|---|---|
| `enable_alertmanager` | bool | `true` | Aktifkan deployment Alertmanager |
| `enable_ha_alertmanager` | bool | `false` | Aktifkan cluster gossip multi-node Alertmanager |
| `alertmanager_port` | int | `9093` | Port listen web UI + API Alertmanager |
| `alertmanager_tag` | string | `"v0.27.0"` | Docker image tag |
| `alertmanager_data_dir` | string | `/var/lib/agra/alertmanager` | Path persist data (silences, notification log) |
| `alertmanager_config_dir` | string | `/etc/alertmanager` | Path config file |
| ... (dsb SEMUA variabel dari defaults/main.yml) |
```

TIDAK DIBOLEHKAN ada variabel di defaults/main.yml yang tidak muncul di variables.md.

---

## Step 10 (Opsional): Tambah CLI Command Baru `agra/commands/alertmanager.py` + Register

Jika role baru butuh command sendiri (contoh: `agra alertmanager silence`, `agra alertmanager send-test-alert`), buat module command Python baru.

```bash
touch agra/commands/alertmanager.py
```

Isi minimal dengan click/argparse subcommand. Kemudian **register ke COMMAND_MODULES**:
```python
# agra/cli.py (atau file registry)
COMMAND_MODULES = [
    "agra.commands.check",
    "agra.commands.genpwd",
    ...
    "agra.commands.alertmanager",   # TAMBAHKAN BARIS INI
]
```

Jika role tidak butuh command spesifik (Alertmanager: cukup deploy via tag `-t alertmanager`), Step ini boleh dilewati. Jangan paksa buat command untuk hal yang bisa dilakukan dengan tag role biasa.

---

## Step 11: Molecule Test — Curl Healthy 200 OK

Buat scenario molecule default untuk role alertmanager:
```bash
cd ansible/roles/alertmanager
molecule init scenario default -d docker
# Edit molecule/default/converge.yml, verify.yml, molecule.yml
```

Contoh `verify.yml` — WAJIB cek health endpoint return 200 OK:
```yaml
---
# molecule/default/verify.yml
- name: Verify
  hosts: all
  gather_facts: false
  tasks:
    - name: "Alertmanager health endpoint /-/healthy return 200"
      uri:
        url: "http://127.0.0.1:{{ alertmanager_port }}/-/healthy"
        method: GET
        status_code: 200
        return_content: true
      register: am_health

    - name: "Fail jika health check tidak OK"
      assert:
        that:
          - am_health.status == 200
        fail_msg: "Alertmanager unhealthy! Status={{ am_health.status }}. Body={{ am_health.content }}"
```

Jalankan test:
```bash
molecule test -s default
# PASS → create, prepare, converge, idempotence, verify, destroy
```

Step 11 GAGAL jika test idempotence (converge ke-2) `changed > 0` — kembali ke Step 3/6 perbaiki logic idempotency.

---

## Step 12: Test Idempotency 2x Run + Submit PR + Checklist

Langkah final sebelum submit PR:

1. **Test Idempotency 2x deploy full stack** dengan role alertmanager enabled. Run pertama deploy → run kedua command sama HARUS `changed=0` pada Alertmanager tasks (gather_facts boleh changed, task lain NO):
   ```bash
   agra deploy -i inventory/all-in-one-with-alertmanager -t alertmanager -v
   # catat jumlah changed
   agra deploy -i inventory/all-in-one-with-alertmanager -t alertmanager -v
   # EXPECTED changed=0 pada seluruh task alertmanager (termasuk download binary)
   ```

2. **Jalankan PR Checklist dari contributing.md §5.** Ceklis SEMUA 8+ item dari:
   - [ ] Variabel di variables.md terupdate
   - [ ] Idempotency pass
   - [ ] Safety guard (jika command destruktif)
   - [ ] Tidak campur docker/native di file task sama
   - [ ] TIDAK PERNAH install/provisioning MySQL/PostgreSQL
   - [ ] Linter clean
   - [ ] Conventional commits format

3. **Submit PR** dengan format title `feat(roles): add alertmanager docker role` sesuai conventional commits.

---

## ⚠️ FOOTER: HARD WARNING — BOUNDARY SCOPE

**JANGAN PERNAH — DALAM KONDISI APAPUN — membuat role atau task dalam role yang melakukan instalasi, provisioning, setup replication, manajemen backup dump, atau HA management terhadap server database MySQL, MariaDB, PostgreSQL, atau database relational manapun.**

Ini adalah aturan boundary scope terkeras di project agra (lihat architecture.md §7). Alasan: deployment database adalah domain terpisah yang sangat kompleks. Scope agra HANYA monitoring stack (visualisasi, metrics, alerting, reverse proxy).

Jika role kamu membutuhkan koneksi database (contoh: Grafana butuh PostgreSQL sebagai backend), role HANYA BOLEH melakukan:
- `wait_for` host:port untuk memastikan reachable
- Inject connection string dan credential ke config file
- Validasi credential bisa connect (opsional)

Role **TIDAK BOLEH** melakukan:
- `apt install mysql-server` / `yum install postgresql`
- `mysql_db` / `postgresql_db` Ansible module untuk create database
- Setup Galera Cluster, Patroni, repmgr, atau orchestrasi replication DB apapun
- `mysqldump` / `pg_dump` untuk tujuan provisioning DB baru

Jika kamu menemukan dirimu perlu melakukan hal diatas untuk role yang sedang kamu buat, **itu adalah tanda bahwa fitur tersebut di luar scope agra** — sebaiknya buat project terpisah yang fokus ke provisioning database, lalu gunakan agra sebagai layer monitoring di-ATAS-nya.
