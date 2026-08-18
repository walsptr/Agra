# Verification Checklist — Fix Grafana Deployment Password Usage (Default admin/admin Bug)

## Checkpoints Syntax & YAML Parsing
- [x] Checkpoint 1: `ansible-playbook deploy.yml --syntax-check -i inventory/all-in-one` rc=0 TANPA ERROR (Task 1, Task 6).
- [x] Checkpoint 2: `python3 -c "import yaml; list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/main.yml'))); list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/docker.yml'))); list(yaml.safe_load_all(open('ansible/roles/grafana/tasks/config.yml')));"` rc=0 — 4 file task Grafana YAML valid.
- [x] Checkpoint 3: Precheck TIDAK REGRESI: `ansible-playbook precheck.yml --syntax-check -i inventory/all-in-one` rc=0 (commit 8786c95 tetap work).
- [ ] Checkpoint 4: `ansible-lint ansible/roles/grafana/tasks/*.yml ansible/playbooks/deploy.yml` 0 fatal errors (opsional).

## Checkpoints AC-1: Passwords.yml Loading HARD-FAIL (deploy.yml)
- [x] Checkpoint 5: deploy.yml SEMUA 7 play (Step 1 common → Step 6 keepalived → Step 7 Summary) TIDAK ADA LAGI baris `failed_when: false` pada task include_vars passwords.yml. grep -R "failed_when: false" deploy.yml → 0 match untuk include_vars block.
- [x] Checkpoint 6: Tiap play memiliki task assertion baru "Precheck deploy: HARD FAIL assertion include_vars /etc/agra/passwords.yml" dengan that clause: grafana_admin_password is defined, grafana_secret_key is defined, len>0.
- [ ] Checkpoint 7: Test negative: Rename sementara /etc/agra/passwords.yml → /tmp/_bak.yml, run deploy grafana → FAIL FATAL (rc≠0) SEBELUM role grafana di-apply dengan pesan error: "Load /etc/agra/passwords.yml GAGAL! Jalankan agra genpwd". Restore file setelah test.

## Checkpoints AC-2: Deploy FAIL-FAST sebelum container start (password invalid → no start)
- [x] Checkpoint 8: docker.yml (atau main.yml sesuai Task3 move) memiliki task assertion "FAIL-FAST ASSERTION Password Policy SEBELUM Container Start" dengan 5 that clause: len>0, != 'admin', len>=8, secret len>=16, not startswith CHANGE_ME.
- [ ] Checkpoint 9: Test negative 1: deploy dengan --extra-vars 'grafana_admin_password=admin' → assertion FAIL FATAL di task fail-fast. `docker ps | grep agra-grafana` → EMPTY (container TIDAK DIMULAI).
- [ ] Checkpoint 10: Test negative 2: deploy dengan --extra-vars 'grafana_admin_password=1234567' (7 chars) → assertion FAIL. Container tidak ada.
- [x] Checkpoint 11: Safety set_fact TIDAK ADA LAGI ternary fallback ke "admin". grep roles/grafana/ -rn "ternary.*admin.*grafana_admin_password" → 0 match. Fallback sekarang HANYA string kosong yang kemudian assertion fail.

## Checkpoints AC-6: grafana.ini SINKRON dengan Docker env vars
- [x] Checkpoint 12: Urutan task main.yml BENAR: PRE COMPUTE 1/3 → 2/3 → 3/3 → Safety set_fact _gf_safe_* → FAIL-FAST assertion Password Policy → Debug Masking Summary → include_tasks config.yml → include_tasks docker.yml. list-tasks deploy --tags grafana menampilkan urutan ini.
- [x] Checkpoint 13: grafana.ini.j2 [security] section baris 46-48 MENGGUNAKAN `_gf_safe_admin_user`, `_gf_safe_admin_password`, `_gf_safe_secret_key` (bukan raw grafana_admin_password tanpa sanitize). Rendered file di managed node /etc/grafana/grafana.ini berisi value SAMA PERSIS dengan docker inspect env GF_SECURITY_ADMIN_PASSWORD.
- [ ] Checkpoint 14: Docker run env var line 92-93 docker.yml JUGA menggunakan _gf_safe_admin_user dan _gf_safe_admin_password. diff rendered grafana.ini value vs env var → IDENTIK.

## Checkpoints AC-3 + AC-5: grafana-cli Reset Password Inside Container (CRITICAL!)
- [x] Checkpoint 15: docker.yml memiliki task "Wait container healthy state" ANTARA task start container DAN reset password cli. Task ini MAX 60 retry × 2 sec = 120 sec wait.
- [x] Checkpoint 16: docker.yml memiliki task "SET ADMIN PASSWORD INSIDE CONTAINER via grafana-cli" dengan:
  - (a) `no_log: true` active → password tidak ter-print ke log.
  - (b) Script 3 step: VERIFY current via /api/login SUDAH SAMA? → exit PASSWORD_ALREADY_MATCHED. Jika TIDAK SAMA → grafana-cli reset-admin-password → VERIFY ULANG HTTP 200.
  - (c) `changed_when: "'PASSWORD_UPDATED_VIA_GRAFANA_CLI_SUCCESS' in stdout"` → idempotent.
- [ ] Checkpoint 17: Test AC-3: Simulasi stale DB. Deploy pertama dengan password default "admin" sambil bypass assertion (gunakan user test lain). Kemudian deploy LAGI dengan valid password P0Y5yE9H8jb7u- dari passwords.yml. Setelah deploy: curl /api/login dengan new password → HTTP 200 OK! curl login dengan old password "admin" → HTTP 401 Unauthorized. Password di sqlite DB BERUBAH.
- [ ] Checkpoint 18: Test AC-5 Idempotency: Deploy 2x berturut-turut dengan password YANG SAMA (valid). Run 1: reset password task changed=true atau false (tergantung initial state). Run 2: reset password task → changed: false (PASSWORD_ALREADY_MATCHED_NO_CHANGE di stdout). Idempotency 100%.

## Checkpoints AC-4: Password Masking Debug Summary
- [x] Checkpoint 19: Task Debug Masking Summary di main.yml menampilkan HANYA prefix 4 char + suffix 4 char + length. Full 14 char password ASLI TIDAK PERNAH muncul secara berurutan di output. grep output ansible log fulltext untuk value P0Y5yE9H8jb7u- → TIDAK KETEMU (cuma prefix P0Y5 dan suffix b7u- muncul terpisah).
- [x] Checkpoint 20: deploy.yml Summary line 167 TIDAK BERISI value plaintext password apapun. Hanya menampilkan: `grafana_admin_password len={{ ... }} chars`, dan fallback admin tidak diizinkan.

## Checkpoints Regresi Global
- [ ] Checkpoint 21: Precheck commit 8786c95 TIDAK REGRESI: Run `agra precheck -i inventory/all-in-one` → Field ADA=True, len=14 OK → precheck PASSED (FAILED=0 semua node).
- [ ] Checkpoint 22: Full deploy 6 step (common → node_exporter → prometheus → grafana → nginx → keepalived) SEMUA assertion include_vars PASS, tidak ada silent fail.
- [ ] Checkpoint 23: Grafana health endpoint hijau setelah deploy, Nginx health check hijau (jika enable_nginx=true).
- [ ] Checkpoint 24: Upgrade scenario: node SUDAH ada deployment LAMA (dengan admin/admin). Run deploy baru → password otomatis berubah tanpa user perlu manual delete grafana.db (backward compat NFR-4).

## Checkpoints Dokumentasi + SCHEMA
- [ ] Checkpoint 25: JIKA menambah variable baru ke defaults/main.yml → SCHEMA.md §2 Grafana di-update 1 baris. Untuk case ini: TIDAK ADA variable baru (hanya restructure task), SCHEMA.md tetap sama, checklist lewat otomatis.
- [ ] Checkpoint 26: git diff --stat: HANYA file yang relevan berubah: deploy.yml, roles/grafana/tasks/main.yml, roles/grafana/tasks/docker.yml, roles/grafana/templates/grafana.ini.j2. TIDAK ada file lain (precheck.yml, globals.yml, passwords.yml, dsb) ikut berubah tanpa perlu.
- [ ] Checkpoint 27: Commit message jelas mention 5 layer fix: (1) silent fail include_vars dihapus, (2) fail-fast assertion password invalid, (3) safety set_fact pindah ke main.yml + admin fallback dihapus, (4) grafana.ini sinkron safe var, (5) grafana-cli reset inside container + idempotent verify.
- [ ] Checkpoint 28: Command user test E2E di dokumentasi: Step-by-step (a) sudo grep grafana_admin_password /etc/agra/passwords.yml → line ada, (b) agra precheck PASS, (c) agra deploy SUCCESS FAILED=0 semua node, (d) curl /api/login dengan passwords.yml value → 200 OK, (e) admin/admin login TIDAK BISA (401).
