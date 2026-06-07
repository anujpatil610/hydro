#!/usr/bin/env sh
set -eu

# Run as the hydro user (NOT via sudo): chmod targets user-owned files under
# $HOME, while ufw is invoked through sudo (passwordless sudo expected).
# LAN subnet allowed to reach the dashboard; override for other networks, e.g.
#   HYDRO_LAN_SUBNET=192.168.1.0/24 ./deploy/hardening.sh
LAN_SUBNET=${HYDRO_LAN_SUBNET:-172.20.0.0/16}

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
  sudo ufw allow ssh
  sudo ufw allow from "$LAN_SUBNET" to any port 8000
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw --force enable
  sudo ufw status verbose
else
  echo "ERROR: ufw not installed; firewall NOT applied. Install with: sudo apt-get install ufw" >&2
  exit 1
fi

echo "Hardening complete."
