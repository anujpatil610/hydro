#!/usr/bin/env sh
# Removes packages that are not needed for the headless hydro controller.
# Run once after first boot and after install.sh completes.
# Usage: sudo ./deploy/cleanup.sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: run as root: sudo ./deploy/cleanup.sh" >&2
  exit 1
fi

# Remove a package only if it is currently installed.
apt_purge() {
  to_remove=""
  for pkg in "$@"; do
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
      to_remove="$to_remove $pkg"
    fi
  done
  if [ -n "$to_remove" ]; then
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get remove --purge -y $to_remove
  fi
}

echo "=== Hydro Pi cleanup — removing packages not required for headless operation ==="

echo "--- GUI / X11 / Wayland ---"
apt_purge \
  xserver-xorg xserver-xorg-core xserver-xorg-input-all xserver-xorg-input-libinput \
  xserver-xorg-video-all xserver-xorg-video-amdgpu xserver-xorg-video-ati \
  xserver-xorg-video-fbdev xserver-xorg-video-nouveau xserver-xorg-video-radeon \
  xwayland x11-common x11-xkb-utils x11-xserver-utils x11proto-dev \
  lightdm lightdm-gtk-greeter \
  openbox pcmanfm mousepad \
  xdg-desktop-portal xdg-desktop-portal-gtk xdg-desktop-portal-wlr \
  rpd-wayland-core rpd-wayland-extras \
  desktop-file-utils

echo "--- Audio / PipeWire ---"
apt_purge \
  pipewire pipewire-bin pipewire-pulse \
  sound-theme-freedesktop

echo "--- VLC ---"
apt_purge \
  vlc vlc-bin vlc-data vlc-l10n \
  vlc-plugin-access-extra vlc-plugin-base vlc-plugin-notify vlc-plugin-qt \
  vlc-plugin-samba vlc-plugin-skins2 vlc-plugin-video-output \
  vlc-plugin-video-splitter vlc-plugin-visualization

echo "--- Education / GUI tools ---"
apt_purge thonny galculator python3-pygame

echo "--- Print / CUPS ---"
apt_purge \
  cups cups-browsed cups-client cups-common cups-core-drivers cups-daemon \
  cups-filters cups-filters-core-drivers cups-ipp-utils cups-pk-helper \
  cups-ppdc cups-server-common printer-driver-hpcups

echo "--- Bluetooth ---"
apt_purge bluez bluez-firmware

echo "--- NFS client ---"
apt_purge nfs-common

echo "--- Debugger ---"
apt_purge gdb

echo "--- Autoremove / clean ---"
DEBIAN_FRONTEND=noninteractive apt-get autoremove -y
apt-get clean

echo "--- Disable services not needed headless ---"
for svc in wayvnc-control glamor-test accounts-daemon udisks2; do
  if systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}"; then
    systemctl disable --now "${svc}.service" 2>/dev/null || true
  fi
done

# Mask cloud-init: first-boot provisioning tool, not needed after setup.
systemctl mask cloud-init cloud-config cloud-final cloud-init-local 2>/dev/null || true

echo "--- Locale cleanup ---"
if command -v localepurge >/dev/null 2>&1; then
  localepurge
else
  echo "  (localepurge not installed — run: sudo apt-get install localepurge)"
fi

echo ""
echo "=== Cleanup complete. Reboot recommended. ==="
df -h /
