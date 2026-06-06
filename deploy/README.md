# Deploy

This folder contains the headless Pi deploy artifacts for Hydro.

## Files

- `hydro.service` — systemd user unit for `hydropi`.
- `install.sh` — local deploy script that syncs the repo, installs Python dependencies, and enables the service.
- `.env.example` — runtime config template for `HYDRO_*` environment variables.

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

   On Git Bash, do not pass unquoted `~/hydro` — the shell expands it to a Windows
   path before the script runs. Use `hydro` (remote home-relative) instead.

4. Verify the service:
   ```sh
   ssh hydropi@172.20.6.122 'systemctl --user status hydro'
   ```

## Notes

- The service uses `~/.config/systemd/user/hydro.service` for the Pi user.
- `HYDRO_MODE` is controlled via `.env`.
- The app serves the built `web/dist` directory from FastAPI when present.
