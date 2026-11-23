import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class Settings:

    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        self.secret_key = os.environ.get("SECRET_KEY", "")
        if not self.database_url or len(self.secret_key) < 32:
            raise RuntimeError(
                "Задайте DATABASE_URL и SECRET_KEY длиной не менее 32 символов в .env"
            )
        self.timezone = os.environ.get("APP_TIMEZONE", "Europe/Moscow")
        self.seed_demo = os.environ.get("SEED_DEMO", "true").lower() == "true"
        self.scheduler_enabled = (
            os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"
        )
        self.cors_origins = os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:8080"
        ).split(",")


settings = Settings()
