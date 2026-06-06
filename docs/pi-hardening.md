# Pi Hardening Guide

## SSH hardening

Manual step — edit `/etc/ssh/sshd_config` and set:

```
PasswordAuthentication no
PermitRootLogin no
AllowUsers hydropi
```

Apply:
```sh
sudo systemctl restart ssh
```

Ensure your public key is already in `~/.ssh/authorized_keys` before disabling password auth.

## Systemd service isolation

Directives added to `deploy/hydro.service`:

| Directive | Effect |
|---|---|
| `NoNewPrivileges=yes` | Prevents the process and children from gaining new privileges via setuid/setgid or capabilities. |
| `PrivateTmp=yes` | Mounts a private `/tmp` and `/var/tmp` for the service; other processes cannot see its temp files. |
| `ProtectSystem=strict` | Mounts the entire filesystem read-only except for explicitly whitelisted paths. |
| `ReadWritePaths=` | Whitelists `~/hydro/data` and `~/hydro/.venv` for write access under `ProtectSystem=strict`. |
| `StartLimitBurst=5` | Caps restart attempts to 5 within `StartLimitIntervalSec=120s` to prevent a crash loop consuming resources. |
| `SyslogIdentifier=hydro` | Tags journal entries with `hydro` so `journalctl -t hydro` filters cleanly. |

## UFW firewall

`deploy/hardening.sh` configures UFW when present:

- Default policy: deny all incoming, allow all outgoing.
- SSH (port 22) allowed from any source.
- Port 8000 (dashboard) allowed only from the LAN subnet `172.20.6.0/24`.

## File permissions baseline

`deploy/hardening.sh` sets:

| Path | Mode | Reason |
|---|---|---|
| `~/hydro/.env` | 600 | Contains secrets; owner-read only. |
| `~/hydro/data` | 700 | Database directory; no group/world access. |
| `~/hydro/deploy/install.sh` | 750 | Executable by owner and group; not world-readable. |

## Bloat removal

The Pi image ships ~1 662 packages for a full desktop environment. The hydro service needs
none of that. `deploy/cleanup.sh` removes the following groups (checking each package is
installed before attempting removal so the script is safe to run multiple times):

| Category | Packages removed | Disk freed (approx.) |
|---|---|---|
| GUI / X11 / Wayland | `xserver-xorg*`, `xwayland`, `lightdm*`, `openbox`, `pcmanfm`, `mousepad`, `xdg-desktop-portal*`, `rpd-wayland-*`, `x11-*`, `desktop-file-utils` | ~120 MB |
| Audio / PipeWire | `pipewire`, `pipewire-bin`, `pipewire-pulse`, `sound-theme-freedesktop` | ~25 MB |
| VLC | `vlc`, `vlc-bin`, `vlc-data`, `vlc-l10n`, `vlc-plugin-*` | ~90 MB |
| Education / GUI tools | `thonny`, `galculator`, `python3-pygame` | ~40 MB |
| Print / CUPS | `cups*`, `cups-filters*`, `cups-ipp-utils`, `cups-pk-helper`, `cups-ppdc`, `printer-driver-hpcups` | ~30 MB |
| Bluetooth | `bluez`, `bluez-firmware` | ~15 MB |
| NFS client | `nfs-common` | ~5 MB |
| Debugger | `gdb` | ~10 MB |

`apt-get autoremove` is run afterward to clean up orphaned libraries pulled in by the above.

### Services disabled/masked

| Service | Reason |
|---|---|
| `wayvnc-control` | VNC remote desktop — not needed headless. |
| `glamor-test` | GPU test service — not needed after boot. |
| `accounts-daemon` | Desktop account management. |
| `udisks2` | Desktop disk management. |
| `cloud-init` (all 4 units) | First-boot provisioning; masked so it never re-runs and overwrites config. |

### Locale data

340 MB of locale files are installed by default. Install `localepurge` and configure it to
keep only `en_US.UTF-8` to recover most of that space:

```sh
sudo apt-get install localepurge
# configure to keep en_US.UTF-8, then:
sudo localepurge
```

`deploy/cleanup.sh` calls `localepurge` automatically if it is already installed.

### Usage

```sh
sudo ./deploy/cleanup.sh
sudo reboot
```

## Verify checklist

Run these after hardening to confirm it worked:

```sh
# 1. Service is active
systemctl --user status hydro

# 2. .env is owner-read only
ls -la ~/hydro/.env

# 3. Firewall is active and rules are correct
ufw status

# 4. Password auth is rejected
ssh -o PasswordAuthentication=no hydropi@172.20.6.122

# 5. Dashboard responds on LAN
curl http://172.20.6.122:8000/health

# 6. Confirm bloat packages are gone
for pkg in vlc thonny xserver-xorg lightdm cups-daemon bluez; do
  dpkg-query -W -f='${Package}: ${Status}\n' "$pkg" 2>/dev/null || echo "$pkg: not installed (good)"
done
```
