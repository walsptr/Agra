# Fix Grafana Deployment Password Usage (Default admin/admin Bug) - The Implementation Plan (Decomposed & Prioritized Task List)

## [x] Task 0: Inspect pipeline linting YAML & confirm 6 bugs root cause
- **Priority**: high
- **Depends On**: None
- **Description**:
  - Verify 6 bugs: (1) deploy.yml include_vars failed_when:false silent fail, (2) role defaults grafana_admin_password="" overriding passwords.yml jika undefined, (3) Safety set_fact ternary fallback ke "admin", (4) grafana.ini.j2 raw var tidak sinkron dengan env docker, (5) MISSING grafana-cli reset task inside container post-start, (6) password full plaintext printed di summary deploy.yml line 167 tanpa masking.
  - Snapshot baseline pre-change diff untuk compare setelah fix.
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-0.1: `ansible-playbook ansible/playbooks/deploy.yml --syntax-check -i localhost,` rc=0 SEBELUM perubahan.
  - `programmatic` TR-0.2: `python3 -c "import yaml; list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/docker.yml')))"` rc=0 SEBELUM.
- **Notes**: Task ini SELESAI, 6 bugs teridentifikasi, snapshot baseline dilakukan.

## [x] Task 1: deploy.yml include_vars passwords.yml — HAPUS `failed_when: false` (HARD FAIL, AC-1)
- **Priority**: high
- **Depends On**: Task 0
- **Description**:
  - Di **SETIAP play deploy.yml (Steps 1-6 + Summary)**: Ubah task pre_tasks "Load globals.yml + passwords.yml": HAPUS 2 baris: (a) `failed_when: false` dan (b) `changed_when: false` TIDAK dihapus (tetap changed false karena tidak merubah state). TAMBAHKAN 2 baris baru: (1) `ignore_errors: false` (default) + (2) `register: _deploy_include_vars`. DI BAWAH task include_vars: TAMBAHKAN task baru `Precheck deploy: include_vars /etc/agra/passwords.yml HARD FAIL assertion` dengan:
    ```yaml
    - name: 'Precheck deploy: HARD FAIL assertion include_vars /etc/agra/passwords.yml'
      ansible.builtin.assert:
        that:
          - grafana_admin_password is defined
          - grafana_secret_key is defined
          - grafana_admin_password | string | length > 0
        fail_msg: |
          ┌──────────────────────────────────────────────────────────────────────┐
          │ DEPLOY BLOKIR: /etc/agra/passwords.yml TIDAK BERHASIL di-load!       │
          │ grafana_admin_password / grafana_secret_key UNDEFINED (kosong).      │
          │                                                                      │
          │ Penyebab umum:                                                       │
          │   1. /etc/agra/passwords.yml TIDAK ADA (belum pernah run genpwd)     │
          │   2. chmod file salah (bukan 0600) / owner bukan root:root           │
          │   3. YAML passwords.yml syntax error (indent salah, dsb)             │
          │                                                                      │
          │ SOLUSI: Jalankan urutan ini DI CONTROL NODE sebelum deploy:          │
          │   1. sudo ls -la /etc/agra/passwords.yml                             │
          │   2. sudo chown root:root /etc/agra/passwords.yml                    │
          │   3. sudo chmod 0600 /etc/agra/passwords.yml                         │
          │   4. (JIKA BELUM ADA) agra genpwd (idempotent, generate random 14c)  │
          │   5. VERIFIKASI: agra precheck -i inventory/....yml (pastikan PASS)  │
          │   6. SETELAH ITU baru jalankan: agra deploy -i inventory/....yml     │
          └──────────────────────────────────────────────────────────────────────┘
        success_msg: '✅ include_vars /etc/agra/passwords.yml BERHASIL: grafana_admin_password terdefinisi (len={{ grafana_admin_password | length }} chars).'
      run_once: true
      delegate_to: localhost
      become: true
      become_user: root
      tags: ['deploy', 'config', 'precheck', 'passwords']
    ```
  - PERHATIAN: Task assertion INI HARUS ADA di SETIAP play deploy (6 play + summary 1 = 7x). Jangan cuma di Step 4 Grafana saja, karena Step 2/3/5/6 juga butuh secret (mis. keepalived_auth_pass).
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: SEMENTARA rename `/etc/agra/passwords.yml` → `/tmp/_pwd_bak.yml` (simulasi file tidak ada) → `ansible-playbook ansible/playbooks/deploy.yml --tags grafana -i inventory/all-in-one --syntax-check` LULUS, lalu dry-run dengan file kosong password → HARUS FAIL di assertion include_vars. Setelah itu restore file.
  - `programmatic` TR-1.2: Deploy real dengan passwords.yml valid → assertion di setiap play `success_msg` muncul dengan len>0.
  - `human-judgement` TR-1.3: Review bahwa 7x task assertion SUDAH ADA di SEMUA 6 play Step 1-6 + Summary deploy.yml.

## [x] Task 2: Role defaults/main.yml grafana defaults → Review & Safety set_fact docker.yml HAPUS fallback "admin" (AC-2)
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - Di `ansible/roles/grafana/defaults/main.yml`:
    - Line 58-59 `grafana_secret_key: ""` dan `grafana_admin_password: ""` → BIARKAN (karena ini fallback JIKA include_vars GAGAL, yang sekarang TIDAK BISA terjadi karena Task 1 HARD FAIL sebelum role start). TIDAK USAH dihapus, biarkan untuk backward compat schema.
  - DI `ansible/roles/grafana/tasks/docker.yml`:
    - **UBAH Safety set_fact (line 48-63 existing)**:
      - BARIS LAMA line 51: `_gf_safe_admin_password: "{{ ((grafana_admin_password | default('') | trim | length == 0) | ternary('admin', grafana_admin_password | default('admin'))) | trim }}"`
      - BARIS BARU line 51: `_gf_safe_admin_password: "{{ grafana_admin_password | default('') | string | trim }}"` (TANPA ternary fallback ke "admin"!). Kalau kosong → akan di-fail-fast oleh assertion Task 3 DI BAWAHNYA sebelum container start.
      - BARIS LAMA line 61 fallback secret key: `_gf_safe_secret_key: "{{ ((grafana_secret_key | default('') | trim | length == 0) | ternary('CHANGE_ME_XXXX', grafana_secret_key)) | trim }}"`
      - BARIS BARU line 61: `_gf_safe_secret_key: "{{ grafana_secret_key | default('') | string | trim }}"` (kosongkan tanpa fallback).
  - **DI BAWAH Safety set_fact, TAMBAHKAN TASK BARU FAIL-FAST ASSERTION (AC-2 TARGET):**
    ```yaml
    - name: 'Grafana (Docker) — FAIL-FAST ASSERTION Password Policy SEBELUM Container Start (AC-2: NO admin default, NO empty, NO <8 chars)'
      ansible.builtin.assert:
        that:
          - _gf_safe_admin_password | string | length > 0
          - _gf_safe_admin_password != 'admin'
          - _gf_safe_admin_password | string | length >= 8
          - _gf_safe_secret_key | string | length >= 16
          - not (_gf_safe_secret_key | string).startswith('CHANGE_ME')
        fail_msg: |
          ┌──────────────────────────────────────────────────────────────────────┐
          │ SECURITY BLOCK — DEPLOY DI-BATALKAN sebelum container start!         │
          │                                                                      │
          │ Password grafana_admin_password TIDAK SESUAI POLICY (AC-2):          │
          │   · Panjang karakter: {{ _gf_safe_admin_password | length }}         │
          │       (MINIMAL 8 karakter, sekarang {{ 'OK ✅' if _gf_safe_admin_password | length >= 8 else 'GAGAL ❌ (<8)' }})
          │   · Apakah == "admin" default weak? : {{ _gf_safe_admin_password == 'admin' }}  (HARUS False)
          │   · Apakah value KOSONG?             : {{ _gf_safe_admin_password | length == 0 }}  (HARUS False)
          │   · grafana_secret_key len>=16?      : {{ _gf_safe_secret_key | length }} chars
          │                                                                      │
          │ SOLUSI (Jalankan DI CONTROL NODE):                                   │
          │   $ agra genpwd   (auto-generate random passwords.yml chmod 0600)   │
          │   $ agra precheck -i inventory/....yml   (pastikan assertion PASS)  │
          │   $ agra deploy   -i inventory/....yml   (coba ulang deploy)        │
          └──────────────────────────────────────────────────────────────────────┘
        success_msg: "✅ Grafana Password Policy OK (admin_password len={{ _gf_safe_admin_password | length }}, bukan 'admin', secret_key len={{ _gf_safe_secret_key | length }}). Container akan segera di-start."
      run_once: true
      delegate_to: localhost
      tags: ['grafana', 'docker', 'config', 'security', 'precheck']
    ```
  - HAPUS task Warning debug (line 65-77 existing) karena fallback "admin" sekarang TIDAK PERNAH TERJADI (task assertion fail-fast akan abort sebelum sampai ke warning debug).
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: Temporary override `grafana_admin_password='admin'` via --extra-vars → deploy grafana sampai docker.yml → assertion FAIL FATAL dengan pesan di atas, container TIDAK ADA (docker ps | grep agra-grafana = empty).
  - `programmatic` TR-2.2: Temporary override `grafana_admin_password='1234567'` (7 chars, <8 min) → assertion FAIL → container tidak start.
  - `programmatic` TR-2.3: Passwords.yml valid → assertion success_msg muncul dengan len=14 OK.
  - `human-judgement` TR-2.4: Cek docker.yml — task Warning debug fallback admin SUDAH TERHAPUS (no more admin fallback silently allowed).

## [x] Task 3: grafana.ini.j2 [security] section GUNAKAN _gf_safe_* sinkron dengan env var (AC-6)
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - `ansible/roles/grafana/templates/grafana.ini.j2` line 45-49 existing:
    ```ini
    [security]
    admin_user = {{ grafana_admin_user }}
    admin_password = {{ grafana_admin_password }}
    secret_key = {{ grafana_secret_key }}
    disable_brute_force_login_protection = false
    ```
  - UBAH menjadi (GUNAKAN SAFE VARIABLE YANG SAMA DENGAN DOCKER ENV VAR, dan TAMBAHKAN FILTER TRIM + QUOTE STRING):
    ```ini
    [security]
    admin_user = {{ _gf_safe_admin_user | default(grafana_admin_user) | default('admin') | string | trim }}
    admin_password = {{ _gf_safe_admin_password | default(grafana_admin_password) | string | trim }}
    secret_key = {{ _gf_safe_secret_key | default(grafana_secret_key) | string | trim }}
    disable_brute_force_login_protection = false
    ```
  - CATATAN: Variable `_gf_safe_*` HANYA ADA di scope docker.yml task. Namun grafana.ini.j2 di-render OLEH config.yml task yang DIJALANKAN SEBELUM docker.yml! Jadi variable _gf_safe_* BELUM TERDEFINISI saat config.yml berjalan. FIX URUTAN TASK ROLE main.yml: PINDAHKAN Safety set_fact (baris line 48-63 docker.yml yang sekarang memuat _gf_safe_*) DARI docker.yml KE ATAS, PINDAHKAN KE roles/grafana/tasks/main.yml SETELAH pre compute 3/3, SEBELUM include_tasks config.yml dan docker.yml. SEHINGGA variable _gf_safe_* tersedia untuk BOTH config.yml (render grafana.ini) DAN docker.yml (env var docker run).

  - **Urutan BARU main.yml (line 18-44 disesuaikan):**
    1. Pre compute 1/3 (line 18-25 existing) → _gf_domain_clean dst.
    2. Pre compute 2/3 (line 26-29 existing) → _gf_domain_selected.
    3. Pre compute 3/3 (line 31-38 existing) → grafana_server_domain + grafana_server_root_url TOP LEVEL.
    4. **(BARU PINDAH KE SINI) Task: Grafana Safety set_fact — _gf_safe_admin_user, _gf_safe_admin_password (NO admin fallback), _gf_safe_secret_key (NO CHANGE_ME fallback), _gf_safe_server_domain, _gf_safe_server_root_url, _gf_safe_listen_address.** (DIPINDAHKAN dari docker.yml line 48-63 ke sini, SETELAH grafana_server_domain di-set, SEBELUM config.yml).
    5. **(BARU) Task: Grafana FAIL-FAST ASSERTION Password Policy (dari Task 2, juga dipindah ke main.yml sebelum config.yml/docker mulai)** — agar fail even earlier, sebelum render grafana.ini dan pull docker image.
    6. **(BARU) Task 4 dari spec.md: Grafana PASSWORD MASKING DEBUG SUMMARY (AC-4 target)** — di sini sebelum config.yml. Pindahkan ke main.yml agar tampil di setiap deploy tag grafana.
    7. `include_tasks: config.yml` (line 40-41 existing) → sekarang _gf_safe_* SUDAH ADA → render grafana.ini.j2 AKURAT.
    8. `include_tasks: docker.yml` (line 43-44 existing) → _gf_safe_* SUDAH ADA → env var docker run AKURAT.
  - DI `docker.yml`: HAPUS seluruh block Safety set_fact (line 48-63 sekarang) karena SUDAH DIPINDAH ke main.yml. Di docker.yml HANYA TINGGAL task: image inspect → pull → check container running state → remove mismatch → start container → (BARU Task 4 spec.md grafana-cli reset password inside container).
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-3.1: Deploy dengan valid password. DI managed host: `sudo cat /etc/grafana/grafana.ini | grep -A 4 '^\[security\]'` → `admin_password = P0Y5yE9H8jb7u-` (value BENAR dari passwords.yml). Lalu: `sudo docker inspect agra-grafana | jq -r '.[0].Config.Env[] | select(startswith("GF_SECURITY_ADMIN_PASSWORD="))'` → `GF_SECURITY_ADMIN_PASSWORD=P0Y5yE9H8jb7u-` (KEDUA VALUE SAMA PERSIS, sesuai AC-6).
  - `programmatic` TR-3.2: Urutan task main.yml BENAR: `ansible-playbook ansible/playbooks/deploy.yml --tags grafana -i inventory/all-in-one --list-tasks` → urutan: PRE COMPUTE 1/3 → 2/3 → 3/3 → Safety set_fact → Password assertion fail-fast → Masking debug → include_tasks config.yml → include_tasks docker.yml.
  - `programmatic` TR-3.3: `python3 -c "import yaml; list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/main.yml')))"` rc=0 (YAML syntax PASS).
  - `human-judgement` TR-3.4: Review docker.yml — tidak ada lagi baris Safety set_fact _gf_safe_* (sudah dipindahkan ke main.yml dengan benar).

## [x] Task 4: KRITIS! docker.yml TAMBAHKAN task grafana-cli reset admin password inside container (AC-3, AC-5 idempotency)
- **Priority**: high (critical path, ini ROOT CAUSE UTAMA user "masih admin/admin")
- **Depends On**: Task 3 (karena butuh _gf_safe_admin_password dari main.yml)
- **Description**:
  - Di `ansible/roles/grafana/tasks/docker.yml`, SETELAH task `Grafana (Docker) - Start container` (line 79 existing yang sekarang menjadi start container) — TAMBAHKAN 2 TASK BARU SECARA BERURUTAN:
    1. **TASK BARU 1/2 — Wait container HEALTHY sebelum reset password (grafana-cli butuh sqlite DB siap!):**
       ```yaml
       - name: 'Grafana (Docker) — Wait container healthy state (health check /api/health green) SEBELUM reset password via cli'
         ansible.builtin.shell:
           cmd: |
             RUNTIME=$(command -v podman >/dev/null 2>&1 && echo podman || echo docker)
             TRIES=0
             MAX=60
             while [ $TRIES -lt $MAX ]; do
               STATE=$($RUNTIME inspect --format='{{'{{'}}.State.Health.Status{{'}}'}}' {{ grafana_container_name }} 2>/dev/null || echo "starting")
               if [ "$STATE" = "healthy" ]; then echo "HEALTHY_TRIES=$TRIES"; exit 0; fi
               TRIES=$((TRIES+1))
               sleep 2
             done
             echo "TIMEOUT_UNHEALTHY_AFTER_120s"; exit 1
         register: _gf_wait_healthy
         changed_when: false
         retries: 2
         delay: 10
         until: _gf_wait_healthy is succeeded
         tags: ['grafana', 'docker', 'container', 'healthcheck', 'passwords']
       ```
    2. **TASK BARU 2/2 — Reset admin password INSIDE container via grafana-cli (IDEMPOTENCY GUARANTEED with LOGIN VERIFY changed_when!):**
       ```yaml
       - name: 'Grafana (Docker) — SET ADMIN PASSWORD INSIDE CONTAINER via grafana-cli (GRAFANA BEHAVIOR FIX: env var IGNORED for existing user in sqlite!)'
         ansible.builtin.shell:
           cmd: |
             RUNTIME=$(command -v podman >/dev/null 2>&1 && echo podman || echo docker)
             TARGET_PW='$(_gf_safe_admin_password_escaped)' # diisi via Ansible var escape
             # STEP 1: VERIFY current password inside DB SUDAH SAMA? (idempotency: login via API)
             HTTP_CODE=$($RUNTIME exec {{ grafana_container_name }} bash -c '
               curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:{{ grafana_port }}/api/login \
                 -H "Content-Type: application/json" \
                 -d "{\"user\":\"{{ _gf_safe_admin_user }}\",\"password\":\"'"${TARGET_PW}"'\"}"
             ' 2>/dev/null || echo "000")
             if [ "$HTTP_CODE" = "200" ]; then
               # SUDAH SAMA! -> NO CHANGE idempotent exit
               echo "PASSWORD_ALREADY_MATCHED_NO_CHANGE"; exit 0
             fi
             # STEP 2: TIDAK SAMA -> GUNAKAN grafana-cli admin reset-admin-password (modify DB directly!)
             $RUNTIME exec {{ grafana_container_name }} \
               grafana-cli admin reset-admin-password "${TARGET_PW}" 2>&1 | tail -3
             # STEP 3: VERIFY ULANG via HTTP API login call dengan NEW password → 200 OK?
             sleep 2
             HTTP_CODE2=$($RUNTIME exec {{ grafana_container_name }} bash -c '
               curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:{{ grafana_port }}/api/login \
                 -H "Content-Type: application/json" \
                 -d "{\"user\":\"{{ _gf_safe_admin_user }}\",\"password\":\"'"${TARGET_PW}"'\"}"
             ' 2>/dev/null || echo "000")
             if [ "$HTTP_CODE2" != "200" ]; then
               echo "ERROR_RESET_FAILED_VERIFY_HTTP=$HTTP_CODE2"; exit 2;
             fi
             echo "PASSWORD_UPDATED_VIA_GRAFANA_CLI_SUCCESS_HTTP_200_VERIFIED"
         register: _gf_cli_reset_pw
         changed_when: "'PASSWORD_UPDATED_VIA_GRAFANA_CLI_SUCCESS' in _gf_cli_reset_pw.stdout"
         failed_when: "'ERROR_RESET_FAILED_VERIFY' in _gf_cli_reset_pw.stdout or _gf_cli_reset_pw.rc not in [0,2]"
         vars:
           # ESCAPE special chars password via to_json (menghindari injection shell single/double quote di bash)
           _gf_safe_admin_password_escaped: "{{ _gf_safe_admin_password | to_json | regex_replace('^\"', '') | regex_replace('\"$', '') }}"
         no_log: true
         tags: ['grafana', 'docker', 'container', 'passwords', 'idempotent']
       ```
  - **PENTING**: `no_log: true` di task reset password (menghindari password value ter-print di Ansible log stdout/stderr — sesuai NFR-2 masking).
  - **IDEMPOTENCY VERIFY**: Script di atas MELAKUKAN login via /api/login DENGAN password TARGET TERLEBIH DAHULU. JIKA SUDAH SAMA (HTTP 200), script langsung exit 0 `PASSWORD_ALREADY_MATCHED_NO_CHANGE` → changed_when FALSE. HANYA JIKA TIDAK SAMA → jalankan grafana-cli reset, kemudian verify lagi. Ini memenuhi AC-5 (idempotency: 2x deploy berturut-turut → changed: false).
  - **BACKWARD COMPAT NFR-4**: Untuk user YANG SUDAH deploy dengan default admin (stale DB state), script ini: Step1 login with new passwords.yml password → HTTP code != 200 (karena DB masih pake admin) → Step2 grafana-cli reset-admin-password → Step3 verify login HTTP 200 OK. TANPA user perlu action manual hapus DB.
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: Simulate stale DB. Step 1: deploy with grafana_admin_password='admin' SEMENTARA (gunakan valid password lain untuk pass assertion Task 2, tapi HAPUS assertion untuk test ini). Step 2: curl API login admin/admin HARUS 200. Step3: revert passwords.yml ke valid "P0Y5yE9H8jb7u-". Step4: deploy LAGI. Step5: curl /api/login dengan password BARU (P0Y5yE9H8jb7u-) → HTTP 200! Step6: curl login dengan password lama (admin) → HTTP 401 Unauthorized! = AC-3 TERPENUHI (password di DB BERUBAH sesuai passwords.yml, bukan env var).
  - `programmatic` TR-4.2: Idempotency test: deploy PERTAMA KALI dengan password valid → reset password task: changed=true (karena password mismatch DB). Deploy KEDUA KALI BERTURUT-TURUT dengan password SAMA: → reset password task: changed=false (PASSWORD_ALREADY_MATCHED_NO_CHANGE). AC-5 TERPENUHI.
  - `human-judgement` TR-4.3: Task reset password MEMILIKI `no_log: true`. grep docker.yml untuk task ini → no_log: true line TERLIHAT. Full password value TIDAK TERSEDIA di ansible log file (masking NFR-2).

## [x] Task 5: Deploy summary & debug — Password masking (AC-4)
- **Priority**: medium
- **Depends On**: Task 4
- **Description**:
  - **Task 5a — DEBUG MASKING SUMMARY di role main.yml (setelah assertion, sebelum config.yml):**
    ```yaml
    - name: 'Grafana — Password Summary DEPLOY TIME (MASKED, NO full plaintext, NFR-2 compliant)'
      ansible.builtin.debug:
        msg: |
          🔐 Grafana Password Status (deploy time — NO full plaintext!):
            · Source of truth          : /etc/agra/passwords.yml (include_vars)
            · grafana_admin_password
              → Panjang karakter       : {{ _gf_safe_admin_password | length }} chars
              → Prefix 4 chars         : {{ _gf_safe_admin_password[:4] | default('N/A') }}
              → Suffix 4 chars         : {{ _gf_safe_admin_password[-4:] | default('N/A') }}
              → BUKAN "admin"          : {{ _gf_safe_admin_password != 'admin' }}
              → Length >= 8 chars      : {{ _gf_safe_admin_password | length >= 8 }}
            · grafana_secret_key
              → Panjang karakter       : {{ _gf_safe_secret_key | length }} chars
              → Prefix 4 chars         : {{ _gf_safe_secret_key[:4] | default('N/A') }}
              → Suffix 4 chars         : {{ _gf_safe_secret_key[-4:] | default('N/A') }}
              → Contains CHANGE_ME?    : {{ _gf_safe_secret_key.startswith('CHANGE_ME') if _gf_safe_secret_key is defined else True }}
              → Length >= 16 chars     : {{ _gf_safe_secret_key | length >= 16 }}
            · ⚠ Password disimpan DI sqlite Grafana DALAM container via grafana-cli reset (bukan cuma env var!).
      changed_when: false
      run_once: true
      delegate_to: localhost
      tags: ['grafana', 'config', 'debug', 'passwords']
    ```
  - **Task 5b — Fix deploy.yml Summary line 167 (NO FULL PLAINTEXT):**
    - Line 167 existing: `"Default user: {{ grafana_admin_user | default('admin') }} — password: lihat /etc/agra/passwords.yml field grafana_admin_password (default fallback: admin jika belum run genpwd)"`
    - UBAH menjadi: `"Default user: {{ grafana_admin_user | default('admin') }} — grafana_admin_password len={{ grafana_admin_password | default('') | length }} chars (lihat /etc/agra/passwords.yml). DEFAULT ADMIN FALLBACK TIDAK DIIZINKAN (lihat Task 2 assertion fail-fast)."` — TIDAK menampilkan password apapun, cuma lengthnya (sesuai NFR-2 NO FULL PLAINTEXT).
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-5.1: Deploy dengan valid password `P0Y5yE9H8jb7u-` → Debug msg menampilkan: `Prefix 4 chars: P0Y5, Suffix 4 chars: b7u-, Length: 14 chars`. grep log output untuk full `P0Y5yE9H8jb7u-` FULL 14 chars BERURUTAN → TIDAK KETEMU (cuma terpecah prefix dan suffix). AC-4 TERPENUHI.
  - `programmatic` TR-5.2: Deploy playbook RUN FULL sampai summary step 7 → summary line TIDAK BERISI password value plaintext, hanya: `len=14 chars` (hanya panjang). AC-4 NFR-2 TERPENUHI.

## [/] Task 6: SYNTAX CHECK, full E2E linting & YAML validasi, update SCHEMA.md & checklist
- **Priority**: high
- **Depends On**: Task 1,2,3,4,5
- **Description**:
  - **Syntax Check 1**: `ansible-playbook ansible/playbooks/deploy.yml --syntax-check -i inventory/all-in-one` → rc=0.
  - **Syntax Check 2**: `python3 -c "import yaml; list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/main.yml'))); list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/docker.yml'))); list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/config.yml'))); print('All 4 grafana role task files YAML OK')"` → rc=0.
  - **Syntax Check 3**: `ansible-playbook ansible/playbooks/precheck.yml --syntax-check -i inventory/all-in-one` → rc=0 (TIDAK ADA REGRESI dari commit 8786c95 precheck password fix yang lalu).
  - **Update SCHEMA.md Bila perlu** (jika menambah variable baru ke defaults, tambahkan 1 baris ke SCHEMA.md §2 Grafana section). Untuk kasus ini: tidak menambah variable baru, cuma merubah urutan task dan menambah assertion. TIDAK USAH update SCHEMA.md kecuali ada var baru.
  - Commit changes ke git dengan message jelas: `fix(grafana deploy): 5 layer fix default admin/admin credential stale sqlite!`.
  - Push origin main.
- **Acceptance Criteria Addressed**: ALL AC (1-6) — final synthesis validation
- **Test Requirements**:
  - `programmatic` TR-6.1: Semua syntax check 1-3 rc=0 TANPA error.
  - `programmatic` TR-6.2: `ansible-playbook ansible/playbooks/deploy.yml --tags grafana -i inventory/all-in-one --list-tasks 2>&1 | tail -40` → menampilkan SEMUA task baru urutan BENAR: Safety → Assert → Masking → config → docker start → wait healthy → grafana-cli reset.
  - `human-judgement` TR-6.3: Review checklist.md semua checkpoints terpenuhi sebelum push commit.
