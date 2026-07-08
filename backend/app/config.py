from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    gemini_api_key: str = ""
    serp_api_key: str = ""
    anthropic_api_key: str = ""
    environment: str = "development"
    google_redirect_uri: str = "http://localhost:8000/api/gmail/callback"
    frontend_url: str = "http://localhost:3000"
    # Etapa 9 — nuevas fuentes
    mouser_api_key: str = ""
    digikey_client_id: str = ""
    digikey_client_secret: str = ""
    tme_api_key: str = ""
    tme_api_secret: str = ""
    apify_api_token: str = ""
    outscraper_api_key: str = ""
    hunter_api_key: str = ""
    # Etapa 10 — MCP
    mcp_jwt_secret: str = "claria-mcp-secret-change-me-in-production"

    class Config:
        env_file = ".env"


settings = Settings()
