#!/usr/bin/env sh
set -eu

echo "Applying Hydro Pi hardening..."

chmod 600 "$HOME/hydro/.env"
chmod 700 "$HOME/hydro/data"
chmod 750 "$HOME/hydro/deploy/install.sh"

if command -v ufw >/dev/null 2>&1; then
  ufw --force enable
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow ssh
  ufw allow from 172.20.6.0/24 to any port 8000
  ufw status verbose
fi

echo "Hardening complete."
