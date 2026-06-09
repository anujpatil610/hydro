# Deploy

This folder contains the headless Pi deploy artifacts for Hydro.

## Files

- `hydro.service` — systemd user unit for `hydropi`.
- `install.sh` — local deploy script that syncs the repo, installs Python dependencies, and enables the service. It generates `.env` on the Pi from the `HYDRO_*` defaults (see `../.env.example` for the template).
- `hardening.sh` / `cleanup.sh` — firewall + file-permission hardening and headless package cleanup.

## Usage

1. Build the dashboard locally:
   ```sh
   npm --prefix web run build
   ```

2. Deploy to the Pi in mock mode (installs to `~/hydro` on the Pi):
   ```sh
   ./deploy/install.sh hydropi@172.20.6.122
   ```

3. Deploy to the Pi in real mode after wiring is ready:
   ```sh
   ./deploy/install.sh hydropi@172.20.6.122 hydro real
   ```

   An optional fourth argument selects the deployment profile (default
   `profiles/bench.yaml`):
   ```sh
   ./deploy/install.sh hydropi@172.20.6.122 hydro mock profiles/commercial.yaml
   ```

   On Git Bash, do not pass unquoted `~/hydro` — the shell expands it to a Windows
   path before the script runs. Use `hydro` (remote home-relative) instead.

4. Verify the service:
   ```sh
   ssh hydropi@172.20.6.122 'systemctl --user status hydro'
   ```

## Notes

- The service uses `~/.config/systemd/user/hydro.service` for the Pi user.
- `install.sh` enables linger (`loginctl enable-linger`) so the service starts at boot without a login session.
- `HYDRO_MODE` is controlled via `.env`. `install.sh` preserves an existing `.env` across re-deploys (and warns if its mode differs from the requested mode).
- `HYDRO_PROFILE` selects the deployment profile (`profiles/*.yaml`) that declares every device — count, type, binding. The unit file sets a default of `profiles/bench.yaml`; a `HYDRO_PROFILE` line in `.env` overrides it. To switch profiles, edit `.env` and `systemctl --user restart hydro` (topology is resolved at boot only). See `../docs/profile-authoring.md`.
- Sync uses `rsync` when available, else falls back to `tar` over ssh. The tar fallback does **not** delete stale remote files — wipe `~/hydro` first for a clean redeploy.
- The app serves the built `web/dist` directory from FastAPI when present.
