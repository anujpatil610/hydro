"""Runtime configuration from environment / .env (HYDRO_* keys)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HYDRO_", env_file=".env", extra="ignore")

    # Phase 2: the deployment profile selects device count/type/binding.
    # HYDRO_PROFILE. Defaults to the bench rig (Phase-1 parity).
    profile: str = "profiles/bench.yaml"

    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "data/hydro.db"
    calibration_path: str = "data/calibration.json"

    # Fallbacks used only when a profile omits them (every shipped profile sets
    # its own retention_hours / poll_seconds). ``mode`` is unused by the
    # profile path and kept for the legacy build_hal factory only.
    mode: str = "mock"
    retention_hours: int = 24
    poll_seconds: int = 10
    pump_ml_per_min: float = 50.0

    # Sim time-lapse: each poll advances poll_seconds * sim_speed sim-seconds.
    # 1.0 = live; ~360 renders a 35-day grow in ~14 min. Sim mode only; restart to apply.
    sim_speed: float = 1.0

    # Extra dev origins so the Vite dev server reaches the API before mDNS exists.
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://hydro.local:5173",
        "http://hydro.local",
    )
