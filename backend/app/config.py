from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    gemini_api_key: str = ""
    serp_api_key: str = ""
    serper_api_key: str = ""   # Serper.dev (alternativa más barata a SerpAPI)
    anthropic_api_key: str = ""
    environment: str = "development"
    # Si no se define, los jobs automáticos sólo corren en producción. Esto
    # evita que un clon de QA sincronice Gmail o envíe correos por accidente.
    cron_enabled: bool | None = None
    google_redirect_uri: str = "http://localhost:8000/api/gmail/callback"
    frontend_url: str = "http://localhost:3000"
    # OAuth de Google (Gmail). En producción se definen por variable de entorno;
    # en local, si están vacías, se cae al archivo backend/app/credentials.json.
    google_client_id: str = ""
    google_client_secret: str = ""
    # OAuth de Microsoft (Outlook, vía Graph). Mismo patrón que Google: en
    # producción por variable de entorno, sin fallback a archivo local.
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/outlook/callback"
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
    mcp_issuer_url: str = "http://localhost:8000"
    mcp_resource_url: str = "http://localhost:8000/api/mcp"
    mcp_access_token_minutes: int = 60
    mcp_refresh_token_days: int = 30
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,testserver"
    mcp_allowed_origins: str = "http://localhost:*"

    class Config:
        env_file = ".env"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def should_run_cron(self) -> bool:
        if self.cron_enabled is not None:
            return self.cron_enabled
        return self.is_production


settings = Settings()
