from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb+srv://societypuppet920_db_user:IXdBgsweyQqJBoJa@cluster0.agt82ce.mongodb.net/payrolldb"
    JWT_SECRET: str = "change_this_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:3000"
    PAYSTUB_DIR: str = "./paystubs"
    DOC_STORAGE_PATH: str = "./documents"
    APP_ENV: str = "development"
    LOG_FORMAT: str = "text"
    LOG_LEVEL: str = "INFO"
    SSN_ENCRYPTION_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
