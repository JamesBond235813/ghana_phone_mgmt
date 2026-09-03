from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ghana Phone Management"
    environment: str = "development"
    database_url: str = "mysql+aiomysql://user:password@127.0.0.1:3306/ghana_phone"
    jwt_secret: str = "change-me-in-production"
    sms_provider: str = "stub"
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:4174",
        "http://127.0.0.1:4175",
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:4174",
        "http://localhost:4175",
    ]
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
