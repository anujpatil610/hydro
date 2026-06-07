#!/usr/bin/env sh
set -eu

echo "Applying Hydro Pi hardening..."

# Run after install.sh: these paths must already exist. Guard each so a missing
# path fails with an actionable message instead of aborting silently before UFW.
for entry in "$HOME/hydro/.env:600" "$HOME/hydro/data:700" "$HOME/hydro/deploy/install.sh:750"; do
  path=${entry%:*}
  mode=${entry##*:}
  if [ ! -e "$path" ]; then
    echo "ERROR: $path does not exist. Run install.sh first (and let the service create data/)." >&2
    exit 1
  fi
  chmod "$mode" "$path"
done

if command -v ufw >/dev/null 2>&1; then
  # Allow SSH BEFORE enabling, so enabling a default-deny firewall can't lock us out.
  ufw allow ssh
  ufw allow from 172.20.6.0/24 to any port 8000
  ufw default deny incoming
  ufw default allow outgoing
  ufw --force enable
  ufw status verbose
else
  echo "ERROR: ufw not installed; firewall NOT applied. Install with: sudo apt-get install ufw" >&2
  exit 1
fi

echo "Hardening complete."
