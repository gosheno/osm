from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_DB: str = "osm_routes"
    POSTGRES_USER: str = "osm_user"
    POSTGRES_PASSWORD: str = "osm_password"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    OSRM_HOST: str = "osrm"
    OSRM_PORT: int = 5000

    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_USER_AGENT: str = "osm-route-mvp/0.1 contact:local-dev@example.com"
    NOMINATIM_EMAIL: str | None = None
    NOMINATIM_COUNTRY_CODES: str = "ru"
    NOMINATIM_TIMEOUT_S: float = 10.0
    NOMINATIM_MIN_REQUEST_INTERVAL_S: float = 1.1
    NOMINATIM_ACCEPT_LANGUAGE: str = "ru"
    NOMINATIM_DEFAULT_VIEWBOX: str | None = None
    NOMINATIM_DEFAULT_BOUNDED: bool = False
    NOMINATIM_DEFAULT_LIMIT: int = 5

    DEFAULT_CITY: str = "санкт-петербург"
    DEFAULT_COUNTRY_CODES: str = "ru"

    GEOCODER_PROVIDER: str = "nominatim"
    GEOCODER_ENABLE_FALLBACK: bool = True

    OCR_SERVICE_URL: str = "http://ocr:8088"
    OCR_ENGINE: str = "auto"
    OCR_REQUEST_TIMEOUT_S: float = 120.0
    OCR_UPLOAD_DIR: str = "data/imports"
    OCR_SAMPLE_ROUTES_DIR: str = "data/routes"
    OCR_MAX_FILES: int = 10
    OCR_MAX_FILE_SIZE_MB: int = 15

    OPENCAGE_BASE_URL: str = "https://api.opencagedata.com/geocode/v1"
    OPENCAGE_API_KEY: str | None = None
    OPENCAGE_LANGUAGE: str = "ru"
    OPENCAGE_COUNTRYCODE: str = "ru"
    OPENCAGE_LIMIT: int = 3
    OPENCAGE_NO_ANNOTATIONS: bool = True
    OPENCAGE_NO_RECORD: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def osrm_base_url(self) -> str:
        return f"http://{self.OSRM_HOST}:{self.OSRM_PORT}"

    @property
    def country_codes(self) -> str:
        return self.NOMINATIM_COUNTRY_CODES or self.DEFAULT_COUNTRY_CODES


settings = Settings()
