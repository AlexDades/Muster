import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    chroma_db_path: str = os.getenv("CHROMA_DB_PATH", "/data/chroma_db" if os.path.isdir("/data") else "./chroma_db")
    collection_name: str = os.getenv("COLLECTION_NAME", "hr_policies")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    db_path: str = os.getenv("DB_PATH", "/data/muster.db" if os.path.isdir("/data") else "./muster.db")
    uploaded_docs_dir: str = os.getenv("UPLOADED_DOCS_DIR", "/data/uploaded_docs" if os.path.isdir("/data") else "./uploaded_docs")
    api_key: str = os.getenv("MUSTER_API_KEY", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000")
    ms365_tenant_id: str = os.getenv("MS365_TENANT_ID", "")
    ms365_client_id: str = os.getenv("MS365_CLIENT_ID", "")
    ms365_client_secret: str = os.getenv("MS365_CLIENT_SECRET", "")
    ms365_mailbox: str = os.getenv("MS365_MAILBOX", "")
    ms365_redirect_uri: str = os.getenv("MS365_REDIRECT_URI", "http://localhost:8000/ms365/callback")
    ms365_use_real_inbox: bool = os.getenv("MS365_USE_REAL_INBOX", "false").lower() == "true"
    gmail_address: str = os.getenv("GMAIL_ADDRESS", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    gmail_use_inbox: bool = os.getenv("GMAIL_USE_INBOX", "false").lower() == "true"
    allowed_senders: str = os.getenv("ALLOWED_SENDERS", "")
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    ngrok_auth_token: str = os.getenv("NGROK_AUTH_TOKEN", "")


settings = Settings()
