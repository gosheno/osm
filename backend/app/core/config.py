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

    DEFAULT_CITY: str = "санкт-петербург"
    DEFAULT_COUNTRY_CODES: str = "ru"

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
