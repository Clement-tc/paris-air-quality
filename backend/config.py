"""
Central configuration. Reads from environment / .env file.

Why a settings object instead of os.getenv scattered everywhere:
- one place to see every knob the pipeline has
- typed + validated at startup, so a missing API key fails loudly and early
  rather than silently 401-ing halfway through a refresh
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- OpenAQ ---
    # v1/v2 are GONE (HTTP 410 since 2025-01-31). Only v3 works, and it
    # requires a key in the X-API-Key header. Get one at https://explore.openaq.org
    openaq_api_key: str = ""
    openaq_base_url: str = "https://api.openaq.org/v3"

    # Paris bounding box: min_lon, min_lat, max_lon, max_lat
    # Slightly wider than the périphérique to catch near-suburb monitors.
    paris_bbox: str = "2.20,48.80,2.50,48.92"

    # Pollutants we care about (OpenAQ parameter names). Others are still
    # stored, just without a severity category.
    target_parameters: str = "pm25,pm10,no2,o3,so2,co"

    # --- Storage ---
    database_url: str = "sqlite:///./paris_air.db"

    # --- CORS ---
    # Comma-separated list of allowed frontend origins in production
    # (e.g. "https://paris-air-quality.vercel.app"). "*" for local dev.
    frontend_origins: str = "*"

    # --- HTTP behaviour ---
    request_timeout_seconds: float = 30.0
    max_locations: int = 200  # safety cap per refresh

    @property
    def bbox_tuple(self) -> tuple[float, float, float, float]:
        parts = [float(x) for x in self.paris_bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("paris_bbox must be 'min_lon,min_lat,max_lon,max_lat'")
        return tuple(parts)  # type: ignore[return-value]

    @property
    def target_parameter_set(self) -> set[str]:
        return {p.strip().lower() for p in self.target_parameters.split(",") if p.strip()}

    @property
    def frontend_origin_list(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


settings = Settings()
