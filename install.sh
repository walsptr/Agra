#!/bin/bash
set -euo pipefail

echo "Install dependencies..."
pip install -r requirements.txt     # PyYAML >= 6.0
echo "Installation dependencies done."
echo "Install entry point..."
pip install -e .                   # Install entry point → command `agra` langsung tersedia di PATH
echo "Installation entry point done."

# ── System-wide Agra config directory (Kolla-Ansible pattern) ──
sudo mkdir -p /etc/agra/config
sudo mkdir -p /etc/agra/ssl
sudo chmod 0755 /etc/agra /etc/agra/config
sudo chmod 0750 /etc/agra/ssl
# Copy template default globals & passwords DARI REPO ke /etc/agra jika belum ada (idempotent no-clobber)
[ -f /etc/agra/globals.yml ]   || sudo cp -n ./etc/agra/globals.yml   /etc/agra/globals.yml
[ -f /etc/agra/passwords.yml ] || sudo cp -n ./etc/agra/passwords.yml /etc/agra/passwords.yml 2>/dev/null || true
[ -d /etc/agra/config ]        || sudo cp -rn ./etc/agra/config/*     /etc/agra/config/ 2>/dev/null || true