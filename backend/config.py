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

    # QuickBooks Online OAuth 2.0
    QB_CLIENT_ID: str = ""
    QB_CLIENT_SECRET: str = ""
    QB_REDIRECT_URI: str = "http://localhost:8000/quickbooks/callback"
    QB_SANDBOX: bool = True  # Set to False in production

    # QBXpress integration
    QBXPRESS_API_URL: str = "http://localhost:5001"
    QBXPRESS_FRONTEND_URL: str = "http://localhost:9000"
    PAYROLLOS_BACKEND_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
