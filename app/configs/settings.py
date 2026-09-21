from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    environment: Literal["dev", "staging", "production"] = "dev"

    app_name: str = "Kelola Limbah API"
    debug: bool = False
    database_url: str = "sqlite:///./kelola_limbah.db"

    # Smart Contract Configuration
    certificate_competition_contract: str | None = None
    competition_contract: str | None = None
    treasury_platform_contract: str | None = None
    listing_token_prize_contract: str | None = None
    price_competition_manager_contract: str | None = None
    prize_competition_manager_contract: str | None = None
    fee_manager_contract: str | None = None
    fee_manager_competition_contract: str | None = None
    signer_manager_contract: str | None = None
    signer_manager_certificate_contract: str | None = None
    certificate_manager_contract: str | None = None

    # Web3 / Indexer Configuration
    web3_rpc_url: str = "https://rpc.bohr.life"
    web3_poll_interval: int = 5
    web3_start_block: int | None = None

    stellar_secret_key: str | None = None
    stellar_contract_id: str | None = None
    stellar_rpc_urls: str = "https://soroban-testnet.stellar.org"

    kubo_api_url: str = "http://kubo:5001"
    kubo_gateway_url: str = "http://localhost:8082"

    frontend_base_url: str = "http://localhost:3000"

    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    mail_username: str = "username"
    mail_password: str = ""
    mail_from: str = "test@email.com"
    mail_port: int = 587
    mail_server: str = "smtp.gmail.com"
    mail_from_name: str = "Kelola Limbah"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    mail_use_credentials: bool = True
    mail_validate_certs: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def get_stellar_rpc_list(self) -> list[str]:
        return [url.strip() for url in self.stellar_rpc_urls.split(",") if url.strip()]

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @property
    def is_staging(self) -> bool:
        return self.environment == "staging"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
