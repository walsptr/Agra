<p align="center">
  <img src="./img/logo-light.svg" alt="Agra Logo" width="300" style="max-width: 100%; height: auto;"/>
</p>

<h1 align="center">Agra - Ansible Deployment Monitoring Stack</h1>

Ansible project untuk otomasi deployment dan lifecycle management monitoring stack production-grade. Grafana sebagai pusat visualisasi dashboard, Prometheus sebagai Time Series Database dan scraper engine metrics, serta Node Exporter untuk export OS & hardware metrics.

Mendukung **hybrid deployment mode**: seluruh service bisa di-deploy sebagai Docker container atau native binary/systemd package, tanpa mencampur logic kedua mode dalam satu task file. Setiap operasional (deploy, upgrade, rollback, destroy, restore, backup, restore) dilindungi safety guard berlapis. Licensed under MIT License (see end of file).

## Install

```bash
git clone https://github.com/walsptr/Agra.git && cd Agra
python3 -m venv .venv && source .venv/bin/activate
./install.sh
```

## Quickstart 5 Langkah

1. **Generate Passwords**:
   ```bash
   agra genpwd
   ```

2. **Edit Konfigurasi & Inventory**:
   Edit `$EDITOR etc/agra/globals.yml` — setidaknya 3 variabel berikut:
   ```yaml
   agra_deployment_mode: docker     # docker | native
   enable_ha_grafana: false         # set true jika 2+ node monitoring
   monitoring_vip: 10.0.0.100       # isi jika enable_ha_grafana: true
   ```
   Kemudian edit inventory: pilih `inventory/all-in-one` (single node) atau `inventory/multinode` (multi-node HA).

3. **Preflight Check**:
   ```bash
   agra check -i inventory/all-in-one
   ```

4. **Deploy**:
   ```bash
   agra deploy -i inventory/all-in-one
   ```
   Selesai! Akses dashboard di **https://\<IP\>/grafana** (single-node) atau **https://10.0.0.100/grafana** (HA).

## Command Reference

| COMMAND | FUNGSI | CONTOH |
|---|---|---|
| `agra check` | Jalankan preflight validation (topologi, TLS expiry, konektivitas DB). Read-only, tidak modifikasi host. | `agra check -i inventory/multinode -v` |
| `agra genpwd` | Generate 6 random passwords 14 karakter ke `passwords.yml` (plaintext chmod 0600). Idempotent, tidak overwrite existing kecuali --force. | `agra genpwd --force` |
| `agra deploy` | Deploy/reconfigure monitoring stack (idempotent, run berulang OK). Precheck otomatis jalan duluan. | `agra deploy -i inventory/all-in-one -t grafana` |
| `agra upgrade` | Rolling upgrade serial:1 (standby dulu, master terakhir), max_fail 0. Backup otomatis sebelum upgrade. | `agra upgrade --grafana-tag 11.3.0 --prometheus-tag v2.54.1` |
| `agra rollback` | Rollback ke versi sebelumnya via `--*-tag` atau `-e extra_vars`. Warning eksplisit untuk downgrade major. | `agra rollback --prometheus-tag v2.53.0 --yes` |
| `agra destroy` | Uninstall seluruh service. Safety 2-layer: `--yes-i-really-mean-it` + playbook assert. Default tidak purge data. | `agra destroy --yes-i-really-mean-it --purge-data` |
| `agra backup` | Backup on-demand (`create`) atau lihat daftar backup (`list`). Snapshot Prometheus via Admin API resmi. | `agra backup create --include-prometheus-tsdb` |
| `agra restore` | Restore dari backup. Safety: `--yes-i-really-mean-it` wajib + backup-before-restore otomatis. | `agra restore -n agra-backup-20250801-153000 --yes-i-really-mean-it` |
| `agra tls` | TLS cert lifecycle: `regenerate` (self-signed), `info`, `check` (parse openssl expiry warning). | `agra tls regenerate --days 365 --yes` |

## Link Dokumentasi Lengkap

📚 Dokumentasi mendalam (157+ variabel, arsitektur, cara kontribusi, menambah role/fitur baru): [docs/index.md](./docs/index.md)

---

# MIT License

**Copyright (c) 2025–2026 Agra Contributors**

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

