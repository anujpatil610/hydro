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
```
