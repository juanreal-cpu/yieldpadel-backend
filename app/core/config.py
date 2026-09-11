from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Afluenc.IA | YieldPadel"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./yieldpadel.db"
    HOLD_EXPIRATION_MINUTES: int = 15
    WHATSAPP_VERIFY_TOKEN: str = "yieldpadel_secret_token_2026"
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_GROUP_ID: str | None = None
    CANCELLATION_GRACE_MINUTES: int = 30
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.0-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()