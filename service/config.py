"""Runtime configuration from environment / .env (HYDRO_* keys)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HYDRO_", env_file=".env", extra="ignore")

    mode: str = "mock"
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "data/hydro.db"
    retention_hours: int = 24
    poll_seconds: int = 10
    pump_ml_per_min: float = 50.0
    calibration_path: str = "data/calibration.json"

    # Extra dev origins so the Vite dev server reaches the API before mDNS exists.
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://hydro.local:5173",
        "http://hydro.local",
    )
