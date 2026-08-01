# Command Reference agra

Daftar lengkap 9 perintah CLI `agra` beserta usage, flags, contoh, dan safety notes.

---

## `agra check`

### Usage
```bash
agra check [OPTIONS]
```

### Deskripsi
Jalankan seluruh pre-flight validation secara terpusat dari `playbooks/precheck.yml`. Command ini **read-only**, tidak pernah memodifikasi managed host. Dijalankan otomatis di awal `agra deploy`, `agra upgrade`, `agra rollback` — bisa dipanggil standalone untuk validasi tanpa aksi.

Validasi mencakup: konektivitas ansible + become, ketersediaan `monitoring_vip` untuk HA, reachability database external (mysql/postgresql), expiry TLS cert, ketersediaan ruang disk, validasi format inventory, dan deteksi `passwords.yml` plaintext.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `-i, --inventory <PATH>` | string | auto-detect | Path file inventory (wajib jika tidak `inventory/all-in-one`) |
| `-e, --extra-vars <KV>` | string | — | Extra vars format `key=value` atau `@file.yml` |
| `--no-vault` | bool | false | Skip validasi vault (tidak disarankan production) |
| `--warnings-as-errors` | bool | false | Treat warning sebagai hard fail |
| `-t, --tags <TAGS>` | string | — | Hanya jalankan precheck tag tertentu (mis. `tls`, `ha`) |
| `-l, --limit <HOST>` | string | — | Batasi precheck ke host/subset tertentu |
| `-v, --verbose` | bool/level | 0 | `-v` verbose, `-vv` debug ansible |
| `--format <text\|json>` | string | `text` | Output format (untuk CI/CD parsing) |
| `--timeout <INT>` | int | 30 | Timeout detik per host untuk konektivitas check |

### Contoh
```bash
# Basic — all-in-one
agra check -i inventory/all-in-one

# Multi-node dengan extra vars + warnings as error (CI pipeline)
agra check -i inventory/multinode-prod \
  -e 'monitoring_vip=10.0.0.100' \
  --warnings-as-errors \
  --format json > precheck-result.json

# Hanya cek TLS dan HA
agra check -t tls,ha -v
```

---

## `agra genpwd`

### Usage
```bash
agra genpwd [OPTIONS]
```

### Deskripsi
Generate random password aman (32 karakter URL-safe, cryptographically secure) ke `etc/agra/passwords.yml`. **Idempotent secara default**: field password yang sudah terisi TIDAK ditimpa. Password yang di-generate meliputi 6 field: `vault_grafana_admin_password`, `vault_grafana_database_password`, `vault_grafana_secret_key`, `vault_keepalived_auth_pass`, `vault_backup_s3_access_key`, `vault_backup_s3_secret_key`.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `--vault` | bool | false | Setelah generate → langsung `ansible-vault encrypt` file passwords.yml |
| `--force` | bool | false | **Timpa SEMUA password existing** (wajib hati-hati) |
| `--length <INT>` | int | 32 | Panjang password per field (min 16) |
| `--output <PATH>` | string | `etc/agra/passwords.yml` | Custom output path |
| `--rotate <LIST>` | string | — | Rotate spesifik field saja (comma-separated: `grafana_admin,keepalived_auth_pass`) |
| `--no-special-chars` | bool | false | Hanya alphanumeric (tanpa simbol) |
| `--dry-run` | bool | false | Cetak password ke stdout TANPA menulis file |
| `-y, --yes` | bool | false | Non-interactive skip konfirmasi `--force` |

### Contoh
```bash
# Generate + encrypt langsung (SARANKAN untuk production)
agra genpwd --vault

# Kelihatan passwordnya tanpa tulis file (dev/testing)
agra genpwd --dry-run

# Rotate specific password saja (misal lupa admin grafana)
agra genpwd --rotate grafana_admin --vault -y
```

---

## `agra deploy`

### Usage
```bash
agra deploy [OPTIONS]
```

### Deskripsi
Deploy atau reconfigure seluruh monitoring stack. Playbook utama `ansible/site.yml` dijalankan dengan urutan role: common → node_exporter → keepalived (jika HA) → prometheus → grafana → nginx. **Idempotent**: run berulang kali menghasilkan `changed=0` bila tidak ada perubahan variabel/config.

Precheck otomatis dijalankan paling awal (bisa skip dengan `--no-precheck`, TIDAK DISARANKAN).

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `-t, --tags <TAGS>` | string | — | Hanya run tag tertentu: `common`, `grafana`, `prometheus`, `node_exporter`, `keepalived`, `nginx`, `tls` |
| `--skip-tags <TAGS>` | string | — | Skip tag tertentu |
| `-l, --limit <HOST>` | string | — | Batasi ke host/subset (mis. `-l mon1`) |
| `-e, --extra-vars <KV>` | string | — | Override variabel: `-e 'grafana_tag=11.3.0'` |
| `--no-precheck` | bool | false | Skip precheck (TIDAK DISARANKAN) |
| `--check` | bool | false | Ansible dry-run `--check --diff` — tidak benar-benar ubah host |
| `--diff` | bool | false | Tunjukkan perubahan file line-by-line |
| `-v, --verbose` | level | 0 | `-v` sampai `-vvvv` (connection debug) |
| `--forks <INT>` | int | 5 | Ansible parallelism |
| `-b, --become` | bool | true | Default `become: true` (root) |

### Contoh
```bash
# Deploy penuh all-in-one
agra deploy -i inventory/all-in-one

# Re-configure hanya grafana dengan custom tag
agra deploy -i inventory/all-in-one -t grafana --diff

# Dry-run sebelum upgrade versi
agra deploy -i inventory/multinode \
  -e 'grafana_tag=11.3.0 prometheus_tag=v2.54.1' \
  --check --diff -v
```

---

## `agra upgrade`

### Usage
```bash
agra upgrade [OPTIONS]
```

### Deskripsi
Rolling upgrade dengan safety guard berlapis. Alur: (1) precheck, (2) backup otomatis config + database, (3) simpan versi lama ke `.installed_versions.yml`, (4) rolling `serial: 1`, `max_fail_percentage: 0`, dengan urutan **standby node dulu → MASTER terakhir**, (5) health check setiap node sebelum lanjut.

Satu node gagal health check → seluruh upgrade ABORT (tidak lanjut ke node berikutnya). Bisa resume setelah fix error.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `--grafana-tag <STR>` | string | — | Shortcut upgrade Grafana docker tag |
| `--prometheus-tag <STR>` | string | — | Shortcut upgrade Prometheus docker tag |
| `--node-exporter-tag <STR>` | string | — | Shortcut upgrade Node Exporter tag |
| `--grafana-native-version <STR>` | string | — | Shortcut native version Grafana |
| `--prometheus-native-version <STR>` | string | — | Shortcut native version Prometheus |
| `-e, --extra-vars <KV>` | string | — | Generic extra vars |
| `--no-backup` | bool | false | Skip backup sebelum upgrade (TIDAK DISARANKAN) |
| `--no-precheck` | bool | false | Skip precheck |
| `--no-health-gate` | bool | false | Skip health check antar node (berisiko downtime) |
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `-t, --tags <TAGS>` | string | — | Upgrade spesifik service saja |
| `--yes` | bool | false | Non-interactive skip warning risiko |
| `-v, --verbose` | level | 0 | Verbosity |

### Contoh
```bash
# Upgrade Grafana + Prometheus sekaligus
agra upgrade --grafana-tag 11.3.0 --prometheus-tag v2.54.1 -i inventory/multinode

# Upgrade native mode
agra upgrade --grafana-native-version 11.3.0 -v

# Upgrade hanya node_exporter saja
agra upgrade -t node_exporter --yes
```

### Safety Notes
⚠️ **Upgrade selalu backup otomatis sebelum menulis apapun.** Jangan pakai `--no-backup` kecuali sudah ada backup manual terpisah.

⚠️ **Rolling order standby-first.** Urutan dihitung dari inventory: `groups['monitoring'][1:]` (semua node kecuali pertama = standby) diupgrade DAHULUAN, baru `groups['monitoring'][0]` (MASTER node) TERAKHIR. Ini menjamin MASTER tetap menyajikan traffic selama standby diupgrade.

⚠️ **max_fail_percentage: 0.** Artinya jika 1 node saja gagal health check, seluruh proses upgrade berhenti. Jangan dipaksa lanjut sebelum root cause dianalisa.

---

## `agra rollback`

### Usage
```bash
agra rollback [OPTIONS]
```

### Deskripsi
Kembalikan service ke versi tertentu (biasanya versi sebelum upgrade). Membaca `.installed_versions.yml` di tiap host untuk referensi versi terakhir yang berjalan sukses. Bisa juga versi dispesifikasikan manual via `--*-tag` atau `-e extra_vars`.

Rollback **tidak sama dengan restore data** — rollback hanya mengganti versi biner/image, format data (TSDB Prometheus, schema Grafana) TIDAK diubah. Downgrade lintas major version berisiko inkompatibilitas data → tampilkan warning eksplisit dan sarankan restore backup sebagai alternatif lebih aman.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `--service <NAME>` | string | ALL | Rollback spesifik service saja (grafana/prometheus/...) |
| `--grafana-tag <STR>` | string | — | Pin versi Grafana rollback |
| `--prometheus-tag <STR>` | string | — | Pin versi Prometheus rollback |
| `-e, --extra-vars <KV>` | string | — | Generic extra vars |
| `--from-file <PATH>` | string | — | Baca versi rollback dari manifest backup tertentu |
| `--yes` | bool | false | Skip konfirmasi interaktif (warning downgrade major) |
| `--no-precheck` | bool | false | Skip precheck |
| `--no-backup` | bool | false | Skip safety backup sebelum rollback |
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `-v, --verbose` | level | 0 | Verbosity |

### Contoh
```bash
# Rollback ke versi sebelum upgrade (dari .installed_versions.yml)
agra rollback -i inventory/multinode --yes

# Rollback hanya grafana ke tag tertentu
agra rollback --service grafana --grafana-tag 11.2.0 -v
```

### Safety Notes
⚠️ **Downgrade major version (mis. 11.x → 10.x Grafana) berisiko tinggi inkompatibilitas database/schema.** Jika error muncul setelah rollback, jalankan `agra restore` ke backup sebelum upgrade — itu jalur yang lebih aman daripada rollback major.

⚠️ **Rollback tetap melakukan backup-before-rollback otomatis** ke folder `pre-rollback-<timestamp>` — kecuali `--no-backup`. Ini antisipasi jika rollback sendiri malah memperburuk state.

---

## `agra destroy`

### Usage
```bash
agra destroy [OPTIONS] --yes-i-really-mean-it
```

### Deskripsi
Uninstall seluruh service monitoring: hapus container/systemd unit, hapus firewall rules, bersihkan runtime artifacts. **Default TIDAK menghapus data persist** (Grafana DB, Prometheus TSDB). Data baru dihapus jika eksplisit tambahkan `--purge-data`.

Operasi ini destruktif — **wajib 2-layer safety guard**:
- Layer 1 (CLI): flag `--yes-i-really-mean-it` WAJIB ada, jika tidak CLI abort sebelum memanggil ansible sama sekali.
- Layer 2 (Playbook): assert `destroy_confirm: true` — defense-in-depth jika user mencoba bypass CLI dan run ansible langsung.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `--yes-i-really-mean-it` | bool | — | **WAJIB ADA**. Safety layer 1. |
| `--purge-data` | bool | false | Hapus SEMUA data persist: grafana.db, prometheus TSDB, config. |
| `--purge-config` | bool | false | Hapus config di `/etc/<service>/` (default tetap simpan) |
| `--purge-user` | bool | false | Hapus user+grup `agra` OS |
| `-t, --tags <TAGS>` | string | ALL | Destroy spesifik service saja (mis. `-t grafana`) |
| `-l, --limit <HOST>` | string | ALL | Batasi ke host tertentu |
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `--no-precheck` | bool | false | Skip precheck |
| `--check` | bool | false | Dry-run destroy (lihat apa yang akan dihapus) |
| `-v, --verbose` | level | 0 | Verbosity |

### Contoh
```bash
# Dry-run — lihat apa yang akan dihapus
agra destroy --yes-i-really-mean-it --check -i inventory/all-in-one

# Destroy tapi TETAP SIMPAN data
agra destroy --yes-i-really-mean-it -i inventory/all-in-one

# Destroy SEMUA termasuk data (BENAR-BENAR HAPUS SEMUA)
agra destroy --yes-i-really-mean-it \
  --purge-data --purge-config --purge-user \
  -i inventory/multinode
```

### Safety Notes
⚠️ **SAFETY LAYER 1 + LAYER 2 WAJIB.** Jika kamu menjalankan `ansible-playbook ansible/playbooks/destroy.yml` langsung tanpa flag, playbook akan GAGAL di assert pertama karena `destroy_confirm` tidak diset. Ini disengaja.

⚠️ **Default TIDAK purge data.** Tanpa `--purge-data`, folder `/var/lib/agra/` (grafana.db + prometheus data) TETAP ADA. Kamu bisa `agra deploy` lagi nanti dan data otomatis kembali ter-load.

⚠️ **Jalankan `--check` DULU.** Sebelum destroy beneran, selalu jalankan dengan flag `--check --diff` untuk me-review apa saja yang akan dihapus.

---

## `agra backup`

### Usage
```bash
agra backup <create|list> [OPTIONS]
```

### Deskripsi
Backup on-demand atau lihat daftar backup yang tersedia. Alur `create`: (1) Tentukan node MASTER monitoring, (2) Dump config + Grafana DB + (opsional) Prometheus TSDB via snapshot API ke staging folder `/tmp/agra-backup-staging/`, (3) `fetch` ke control node di `backup_destination_path/<timestamp>/`, (4) Generate `manifest.yml` + checksum, (5) Opsional mirror ke S3, (6) Cleanup backup lama per `backup_retention_days`.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `<subcommand>` | choice | — | `create` atau `list` (wajib) |
| `--include-prometheus-tsdb` | bool | false | **Sertakan snapshot TSDB Prometheus.** Default OFF karena ukuran besar. |
| `--no-prometheus-tsdb` | bool | false | Eksplisit exclude TSDB |
| `--skip-s3` | bool | false | Skip mirror S3 meskipun `backup_s3_enabled: true` |
| `--name <STR>` | string | auto-timestamp | Nama custom folder backup |
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `-e, --extra-vars <KV>` | string | — | Override `backup_destination_path`, dll |
| `--format <text\|json\|table>` | string | `table` | Output format untuk `list` |
| `--limit <N>` | int | 20 | Batasi `list` ke N backup terbaru |
| `--no-retention-cleanup` | bool | false | Skip penghapusan backup lama |

### Contoh
```bash
# Backup config + grafana SAJA (default, cepat, ukuran kecil)
agra backup create -i inventory/all-in-one

# Backup PENUH termasuk TSDB Prometheus (size bisa besar!)
agra backup create --include-prometheus-tsdb -i inventory/multinode

# Lihat daftar backup
agra backup list --limit 10 --format table
```

---

## `agra restore`

### Usage
```bash
agra restore [OPTIONS] --yes-i-really-mean-it
```

### Deskripsi
Restore state dari backup tertentu. Validasi `manifest.yml` dulu (versi service saat backup vs sekarang → warning jika beda), lalu **otomatis jalankan safety backup-before-restore** (folder prefix `pre-restore-`) SEBELUM menimpa state apapun. Baru setelah safety backup selesai, file dari backup asli ditulis kembali ke managed host.

Pilih backup via nama (`-n`) atau path tarball absolute (`-f`).

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `-n, --name <STR>` | string | — | Nama backup dari `agra backup list` |
| `-f, --from-file <PATH>` | string | — | Path absolute ke file tarball backup |
| `--yes-i-really-mean-it` | bool | — | **WAJIB ADA** (safety layer 1) |
| `--no-safety-backup` | bool | false | Skip backup-before-restore (SANGAT TIDAK DISARANKAN) |
| `--restore-prometheus-tsdb` | bool | false | Restore juga TSDB (jika backup include) |
| `--service <NAME>` | string | ALL | Restore spesifik service saja |
| `--ignore-version-mismatch` | bool | false | Skip warning perbedaan versi service backup vs current |
| `-i, --inventory <PATH>` | string | auto | Path inventory |
| `-v, --verbose` | level | 0 | Verbosity |
| `--check` | bool | false | Dry-run restore |

### Contoh
```bash
# Restore dari nama backup
agra restore -n agra-backup-20250801-153000 --yes-i-really-mean-it -i inventory/all-in-one

# Restore dari file tarball spesifik + full TSDB
agra restore -f /var/backups/agra/custom-backup.tar.gz \
  --restore-prometheus-tsdb \
  --yes-i-really-mean-it -v
```

### Safety Notes
⚠️ **Backup-before-restore SELALU jalan otomatis** kecuali `--no-safety-backup`. Jika restore bermasalah, kamu masih punya state tepat sebelum restore berjalan di folder `pre-restore-<timestamp>`.

⚠️ **Version mismatch warning.** Jika backup dibuat saat Grafana 11.2.0 tapi sekarang sudah 11.3.0, restore akan warning (bisa di-ignore dengan `--ignore-version-mismatch`). Lebih aman: rollback ke versi yang sama dulu baru restore.

⚠️ **Manifest file WAJIB ADA.** Jika restore gagal dengan "manifest not found", coba `agra backup list` untuk lihat nama yang benar, atau pakai `-f` ke path tarball yang kamu yakin valid.

---

## `agra tls`

### Usage
```bash
agra tls <regenerate|info|check> [OPTIONS]
```

### Deskripsi
Manajemen siklus hidup sertifikat TLS/HTTPS Nginx. Tiga subcommand:
- **`regenerate`**: Hapus self-signed cert lama, generate yang baru via role nginx (dengan `creates:` guard, jadi idempotent). **Hanya self-signed cert yang boleh disentuh** — custom cert CA-signed user di `tls_cert_path` TIDAK PERNAH dimodifikasi agra.
- **`info`**: Parse openssl cert → cetak Issuer, CN, SAN, Not Before, Not After, signature algorithm.
- **`check`**: Validasi expiry → warning `<30 hari`, critical `<7 hari`. Cocok untuk CI cron.

### Flags List
| Flag | Tipe | Default | Deskripsi |
|---|---|---|---|
| `<subcommand>` | choice | — | `regenerate`, `info`, `check` (wajib) |
| `-c, --cert <PATH>` | string | default tls_cert_path | Path cert explicit |
| `-k, --key <PATH>` | string | default tls_key_path | Path key explicit |
| `--days <INT>` | int | `tls_self_signed_days_valid` | Berlaku cert baru (`regenerate`) |
| `--yes` | bool | false | Skip konfirmasi `regenerate` |
| `--warning-days <INT>` | int | 30 | Threshold warning untuk `check` |
| `--critical-days <INT>` | int | 7 | Threshold critical untuk `check` |
| `--format <text\|json\|nagios>` | string | `text` | Output format untuk `check`/`info` |
| `-i, --inventory <PATH>` | string | auto | Inventory untuk `regenerate` (lewat ansible) |
| `-t, --tags <TAGS>` | string | `nginx,tls` | Tags regenerate |

### Contoh
```bash
# Lihat info cert saat ini
agra tls info

# Check expiry untuk monitoring cron
agra tls check --format nagios
# Exit code: 0=OK, 1=WARNING, 2=CRITICAL

# Regenerate self-signed cert berlaku 1 tahun
agra tls regenerate --days 365 --yes -i inventory/all-in-one
```
