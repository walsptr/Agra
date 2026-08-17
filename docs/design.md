# Design Patterns — Pola Desain Teknis Agra

Dokumen ini menjelaskan pola desain teknis yang **WAJIB diikuti KONSISTEN** di seluruh role, playbook, dan komponen agra. Ini rujukan "bagaimana" implementasi — untuk "apa" dan "kenapa" lihat [architecture.md](./architecture.md).

---

## 1. Router Pattern UTAMA (Isolasi Docker vs Native)

**POLA WAJIB** untuk setiap role service (`grafana`, `prometheus`, `node_exporter`, dst). DILARANG mencampur logic docker/native dalam satu file task yang sama.

Struktur direktori per role:
```
roles/<service>/
├── defaults/main.yml
├── tasks/
│   ├── main.yml       # <<< ROUTER HANYA: assert + include config → docker XOR native
│   ├── validate_ha.yml # (opsional) assert khusus HA
│   ├── config.yml     # SHARED: render config, mkdir, chown — dipakai KEDUA mode
│   ├── docker.yml     # ISOLASI DOCKER SAJA
│   └── native.yml     # ISOLASI NATIVE SAJA
├── handlers/main.yml
├── templates/
│   ├── <service>.yml.j2
│   └── <service>.service.j2  # hanya native
└── README.md
```

**Isi `tasks/main.yml` HANYA ROUTER — tidak ada task lain:**
```yaml
---
# roles/<service>/tasks/main.yml

# (Opsional) Validasi khusus HA jika enable
- include_tasks: validate_ha.yml
  when: enable_ha_<service> | default(false) | bool

# Shared config — dipakai SEMUA deployment (WAJIB, di-include SEBELUM docker)
- include_tasks: config.yml

# Docker deployment
- include_tasks: docker.yml
```

Prinsip:
- `tasks/main.yml` = router saja. Tidak boleh ada task yang benar-benar melakukan sesuatu.
- `tasks/config.yml` = shared 100%. Semua logic config rendering, mkdir, chown disini.
- `tasks/docker.yml` = deployment container. Satu-satunya mode-specific file.

Ini menjamin: logic config terisolasi dari logic deployment container, mudah testing dan maintenance.

---

## 2. first_found Config Override Formula

**MEKANISME INTI** "Kolla-style config override". Setiap render config template WAJIB memeriksa custom template user di `/etc/agra/config/<service>/` DAHULU sebelum fallback ke template default role. Tujuannya: user bisa custom config 100% tanpa fork/edit kode role.

### Formula lookup `first_found`

```yaml
---
# roles/<service>/tasks/config.yml

- name: "Render {{ service }} config"
  template:
    src: "{{ lookup('first_found', search_paths) }}"
    dest: "{{ <service>_config_dir }}/<service>.yml"
    owner: "472"
    group: "472"
    mode: "0640"
  notify: "restart {{ service }}"
  vars:
    search_paths:
      files:
        - "/etc/agra/config/<service>/<service>.yml.j2"
        - "/etc/agra/config/<service>/custom.yml.j2"
        - "<service>.yml.j2"       # <<< FALLBACK: template default dari role
      paths:
        - "{{ role_path }}/templates"
```

### Urutan lookup priority (dari yang PALING diutamakan):

| Prioritas | Path | Keterangan |
|---|---|---|
| 1 (TERATAS) | `/etc/agra/config/<service>/<service>.yml.j2` | User taruh custom template persis nama file default. 100% GANTI seluruh config. |
| 2 | `/etc/agra/config/<service>/custom.yml.j2` | Nama alternatif custom. |
| 3 (TERAKHIR) | `<service>.yml.j2` dari `role_path/templates` | Template default dari role. |

**Aturan tegas:**
- Custom config **menggantikan SELURUH file**, bukan merge partial. Tidak ada "magic merge" yang menyebabkan perilaku tak terduga.
- Setiap service WAJIB punya folder default `etc/agra/config/<service>/` di source tree (boleh kosong atau berisi `.gitkeep`) sebagai dokumentasi bahwa override disana DIDUKUNG.
- Semua render file config (grafana.ini, prometheus.yml, keepalived.conf, nginx site, healthcheck script) WAJIB pakai pola ini. DILARANG `template:` langsung tanpa first_found wrapper.

---

## 3. Priority Config Override (CLI > group_vars > globals.yml)

Sebelum template di-render, variabel sendiri punya urutan override priority (standar Ansible, tapi dikuatkan dengan eksplisit):

```
Priority TERTINGGI → TERENDAH:

 1. CLI: `agra deploy -e 'key=value'`   (extra_vars command line)
 2. `ansible/group_vars/<group>.yml`    (per group inventory)
 3. `ansible/host_vars/<host>.yml`      (per host)
 4. `etc/agra/globals.yml`              (non-secret global user config)
 5. `ansible/roles/<role>/defaults/main.yml`  (default value terendah)
```

Contoh praktis:
```yaml
# 1. globals.yml:   grafana_tag: "11.2.0"
# 2. group_vars/monitoring.yml:  grafana_tag: "11.3.0"
# 3. CLI extra_vars:
agra deploy -e 'grafana_tag=11.4.0'

# HASIL: grafana_tag = 11.4.0  (CLI menang SEMUA)
```

Ini penting untuk upgrade one-off tanpa perlu edit file config permanen.

---

## 4. Keepalived Combined Health Check

Keepalived `vrrp_script` untuk monitoring HA **WAJIB melakukan combined check**: keduanya Grafana DAN Prometheus harus sehat (HTTP 200 OK) agar node dianggap healthy. Jika salah satu gagal → weight turun → VIP pindah.

Filosofi: Node monitoring co-located dianggap gagal **sebagai satu unit** — tidak ada gunanya VIP tetap di node yang Grafana-nya down (walau Prometheus sehat), karena user yang megakses VIP ke `/grafana` akan dapat error.

### Script Health Check Referensi

```bash
#!/usr/bin/env bash
# /usr/local/bin/agra_monitoring_healthcheck.sh
# dipanggil vrrp_script keepalived setiap interval detik

set -o pipefail

# Grafana health
GRAFANA_OK=$(curl -s -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:{{ grafana_port }}/api/health)

# Prometheus health
PROM_OK=$(curl -s -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:{{ prometheus_port }}/-/healthy)

# COMBINED: keduanya HARUS 200
if [ "$GRAFANA_OK" = "200" ] && [ "$PROM_OK" = "200" ]; then
    exit 0    # healthy → weight tetap
else
    exit 1    # unhealthy → weight dikurangi keepalived_weight (-20 default)
fi
```

### Konfigurasi VRRP keepalived.conf terkait:

```
vrrp_script chk_agra_monitoring {
    script "/usr/local/bin/agra_monitoring_healthcheck.sh"
    interval {{ keepalived_check_interval }}    # default 2 detik
    fall     {{ keepalived_fall_count }}         # default 3 (butuh 3x gagal berturut)
    rise     {{ keepalived_rise_count }}         # default 2 (butuh 2x sehat berturut)
    weight   {{ keepalived_weight }}             # default -20
}

vrrp_instance VI_MONITORING_01 {
    ...
    track_script {
        chk_agra_monitoring
    }
}
```

Ini mencegah false-positive failover karena hiccup jaringan sesaat (perlindungan via `fall`/`rise`).

---

## 5. Sqlite HA Sync — Double Buffer Rsync (PRAGMA integrity_check)

Untuk `grafana_database: sqlite` + `enable_ha_grafana: true`, sinkronisasi grafana.db dari MASTER ke standby TIDAK BOLEH `scp`/`rsync` langsung ke file aktif (risiko corrupt bila write terjadi ditengah copy).

Pola **Double Buffer + Integrity Check + Atomic Rename** WAJIB diikuti:

```
   MASTER node (grafana.db WRITE AKTIF)
   │
   │ 1. rsync ke standby → GRAFANA.DB.NEW (bukan ke file aktif)
   ▼
   STANDBY node
     ├── /var/lib/agra/grafana/grafana.db        ← file AKTIF (jangan sentuh dulu)
     └── /var/lib/agra/grafana/grafana.db.new    ← file BARU dari rsync
           │
           │ 2. Jalankan PRAGMA integrity_check:
           │    sqlite3 grafana.db.new "PRAGMA integrity_check;"
           ▼
           HASIL:
           ├─ "ok"     → LANJUT step 3
           └─ "not ok" → ABORT. Hapus .new, exit error.
                               Tetap pakai grafana.db LAMA (tidak corrupt).
           │
           │ 3. Backup file aktif lama ke timestamp:
           │    cp grafana.db → grafana.db.bak-$(date +%Y%m%d-%H%M%S)
           │
           │ 4. Atomic rename (rename() syscall = atomik dalam POSIX):
           │    mv grafana.db.new grafana.db
           ▼
   STANDBY sekarang punya DB konsisten terbaru.
   Next cron 5 menit kemudian ulangi dari awal.
```

### Code snippet Ansible untuk script cron (dijalankan di standby node, tarik dari MASTER via rsync pull):

```yaml
# roles/grafana/tasks/config.yml — HA sqlite job
- name: "Deploy grafana sqlite HA sync script"
  template:
    src: "{{ lookup('first_found', grafana_sync_script_search) }}"
    dest: /usr/local/bin/agra_grafana_sqlite_sync.sh
    mode: "0700"
    owner: "root"
  when:
    - enable_ha_grafana | bool
    - grafana_database == 'sqlite'
    - inventory_hostname != groups['monitoring'][0]  # HANYA DI STANDBY, MASTER TIDAK PERLU
```

Script shell di template:
```bash
#!/bin/bash
set -euo pipefail

MASTER_HOST="{{ groups['monitoring'][0] }}"
DB_PATH="{{ grafana_sqlite_path }}"
SSH_USER="{{ grafana_sqlite_sync_ssh_user }}"

# Step 1: RSYNC ke .new (dari MASTER → standby .new)
rsync -az --delete \
  "${SSH_USER}@${MASTER_HOST}:${DB_PATH}" \
  "${DB_PATH}.new"

# Step 2: Integrity check
CHECK_RESULT=$(sqlite3 "${DB_PATH}.new" "PRAGMA integrity_check;")
if [ "$CHECK_RESULT" != "ok" ]; then
    echo "[$(date)] integrity_check FAILED: $CHECK_RESULT. ABORT sync."
    rm -f "${DB_PATH}.new"
    exit 1
fi

# Step 3: Backup current ke timestamp
TS=$(date +%Y%m%d-%H%M%S)
cp -a "${DB_PATH}" "${DB_PATH}.bak-${TS}"

# Step 4: Atomic rename
mv "${DB_PATH}.new" "${DB_PATH}"

echo "[$(date)] Sync OK. Backup: ${DB_PATH}.bak-${TS}"
```

Ini menjamin standby **tidak pernah** punya file grafana.db setengah corrupt (yang paling buruk terjadi: tetap pakai versi lama 5 menit lalu).

---

## 6. Rolling Upgrade Order — Standby-First, Master-Last

Untuk grup `[monitoring]` multi-node, upgrade WAJIB berjalan `serial: 1` (1 node per giliran) dan `max_fail_percentage: 0` (1 node gagal = SELURUH upgrade ABORT).

Urutan host **TIDAK BOLEH inventory order default** (MASTER duluan). Harus dihitung ulang agar standby node (selain yang pertama) DIUPGRADE DAHULU, MASTER (node pertama, `groups['monitoring'][0]`) DIUPGRADE TERAKHIR.

### Formula Order Upgrade (Jinja snippet di playbook):

```yaml
---
# playbooks/upgrade_monitoring.yml

- name: "Calculate upgrade order: standby groups[1:] FIRST, master groups[0] LAST"
  hosts: localhost
  gather_facts: false
  tasks:
    - set_fact:
        monitoring_upgrade_order: >-
          {{
            (groups['monitoring'][1:] | default([]))
            +
            ([groups['monitoring'][0]] if groups['monitoring'] | length > 0 else [])
          }}

- name: "Rolling upgrade monitoring nodes (standby FIRST, master LAST)"
  hosts: "{{ hostvars.localhost.monitoring_upgrade_order }}"
  gather_facts: true
  become: true
  serial: 1                    # 1 node per giliran
  max_fail_percentage: 0       # 1 node GAGAL = ABORT SEMUA
  vars:
    destroy_confirm: false
  pre_tasks:
    - include_tasks: playbooks/partials/_health_check_pre.yml
  roles:
    - role: common
    - role: prometheus
    - role: grafana
    - role: nginx
    - role: keepalived
  post_tasks:
    - include_tasks: playbooks/partials/_health_check_post.yml
```

**Contoh urutan untuk 3 node monitoring [mon1 (master), mon2, mon3]:**
```
inventory order asli: [mon1, mon2, mon3]
                     ──┬── ─┬── ─┬──
                       │    │    └── idx 2
                       │    └─────── idx 1
                       └──────────── idx 0 (MASTER)

formula upgrade_order = groups[1:] + [groups[0]]
                      = [mon2, mon3] + [mon1]
                      = [mon2, mon3, mon1]
RUN ORDER:  mon2 ➜ mon3 ➜ mon1 (MASTER TERAKHIR)
```

Ini menjamin: selama node standby diupgrade, MASTER node masih menyajikan traffic ke user (karena MASTER megang VIP). Baru setelah semua standby terbukti sehat, MASTER upgrade di langkah terakhir.

---

## 7. Backup Restore Prom TSDB via POST `/api/v1/admin/tsdb/snapshot` RESMI

Prometheus punya folder data TSDB yang **terus ditulis** saat berjalan. **DILARANG KERAS** `tar -czf prometheus_data.tgz /var/lib/agra/prometheus/` saat Prometheus aktif (risiko high chunk corrupt, WAL replay gagal, data hilang).

Untuk backup Prometheus TSDB — **WAJIB pakai Snapshot Admin API RESMI**. `--web.enable-admin-api` SELALU di-aktifkan di setiap deployment Prometheus (walaupun `backup_include_prometheus_tsdb: false`), agar kapan saja bisa snapshot.

### Step Backup TSDB via API:

```
PROM API:  POST http://127.0.0.1:9090/api/v1/admin/tsdb/snapshot
           (skip_head: false, binary defaults)

  ⬇ response:
  {
    "status": "success",
    "data": {
      "name": "20250801T081530Z-<random>"
    }
  }

Folder snapshot di-create di:
  {{ prometheus_data_dir }}/snapshots/20250801T081530Z-<random>/
    ├── chunks_head/    (chunks TSDB frozen — immutable)
    ├── wal/            (Write-Ahead Log frozen)
    ├── queries.active
    └── meta.json
```

### Step Ansible Backup Playbook (MASTER node ONLY):

```yaml
---
# roles/prometheus/tasks/main.yml section backup snapshot

- name: "Prometheus: trigger TSDB snapshot Admin API"
  uri:
    url: "http://127.0.0.1:{{ prometheus_port }}/api/v1/admin/tsdb/snapshot"
    method: POST
    status_code: 200
    return_content: true
  register: prom_snap_result
  run_once: true
  delegate_to: "{{ groups['monitoring'][0] }}"  # MASTER NODE SAJA
  when: backup_include_prometheus_tsdb | bool

- name: "Prometheus: set snapshot folder path fact"
  set_fact:
    prom_snapshot_name: "{{ prom_snap_result.json.data.name }}"
    prom_snapshot_path: "{{ prometheus_data_dir }}/snapshots/{{ prom_snap_result.json.data.name }}"
  run_once: true

- name: "Prometheus: fetch snapshot folder to control node"
  synchronize:
    src: "{{ prom_snapshot_path }}/"
    dest: "{{ backup_control_node_path }}/prometheus/snapshot/"
    mode: pull
  run_once: true
  delegate_to: "{{ groups['monitoring'][0] }}"
```

### Restore Procedure:

1. Stop Prometheus service di target node (docker stop / systemctl stop)
2. Hapus (atau rename ke `.old`) folder `chunks_head/` + `wal/` LAMA di `prometheus_data_dir`
3. Copy isi snapshot backup yang mau di-restore ke folder `prometheus_data_dir` (menggantikan chunks_head dan wal)
4. Jalankan `promtool tsdb list` atau start Prometheus
5. Prometheus akan rebuild index dari snapshot frozen → siap query data lama

### Grafana Backup Restore:

Untuk Grafana: backup via grafana-cli `backup` command resmi, atau `sqlite3 .backup` (untuk sqlite backend), atau dump SQL mysql/pg (untuk backend external). Semua ditangani playbook `backup.yml` bagian Grafana terpisah dari Prom snapshot.

**Catatan penting**: Backup Prometheus TSDB MASTER only (delegate ke `groups['monitoring'][0]`) — karena standby punya data yang sama secara penuh (full duplication model). Cukup backup satu kali tidak perlu semua node.
