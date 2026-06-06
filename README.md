# Hydro

Headless Raspberry Pi 5 hydroponics controller. Reads pH / TDS / water temperature,
logs to SQLite (24h retention), serves a live dashboard, and allows manual pump dosing.

See `PHASE1_BRIEFING.md` for scope and `docs/PHASE1_PLAN.md` for the build plan.

## Modes

`HYDRO_MODE` selects the hardware layer:

- `mock` — synthetic sensors/actuators. Runs on any machine. Default for development.
- `real` — ADS1115 + DS18B20 + relay-driven pump. Pi only.

## Quickstart (mock mode, any machine)

```bash
uv sync                 # create venv + install backend deps (laptop-friendly)
uv run ruff check .     # lint
uv run pytest -q        # tests
```

Real-mode hardware drivers live in the optional `hardware` extra and install only on the Pi
(`uv sync --extra hardware`).

## Layout

| Path | Layer |
|---|---|
| `hal/` | Sensor + actuator abstraction (mock/real) |
| `service/` | FastAPI + SQLite + 10s poller + REST API |
| `web/` | Vite + React dashboard |
| `scripts/` | Calibration + hardware sanity helpers |
| `deploy/` | systemd unit + install script |

## Deploy

After `web` is built, deploy the repo to the Pi and enable the user service:

```sh
./deploy/install.sh hydropi@172.20.6.122
ssh hydropi@172.20.6.122 'systemctl --user status hydro'
```

For the wired Pi setup, pass `real` mode (remote path is `~/hydro` on the Pi):

```sh
./deploy/install.sh hydropi@172.20.6.122 hydro real
```
