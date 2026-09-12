"""
Central configuration for the Artisan Market Linkage backend.
All secrets/keys are read from environment variables — never hard-code them.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Database ---
    database_url: str = "postgresql+psycopg2://artisan:artisan@localhost:5432/artisan_db"

    # --- Storage ---
    media_root: str = "./media"          # where committed images/audio live
    chunk_tmp_root: str = "./media/_chunks"  # in-progress resumable uploads

    # --- Bhashini ASR (Member 5) ---
    bhashini_api_url: str = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/compute"
    bhashini_udyat_key: str = ""
    bhashini_inference_key: str = ""
    bhashini_pipeline_id: str = ""

    # --- Whisper fallback (Member 5) ---
    openai_api_key: str = ""
    whisper_model: str = "whisper-1"

    # --- LLM extraction (Member 5) ---
    extraction_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""

    # --- Pricing defaults (Member 6) ---
    default_wage_benchmark_per_hour: float = 45.0   # INR/hour, overridable per category
    default_market_adjustment_pct: float = 0.15     # 15% margin over cost

    # --- ONDC / Beckn (Member 6) ---
    ondc_bpp_id: str = "artisan-marketlink.ondc.example"
    ondc_bpp_uri: str = "https://artisan-marketlink.ondc.example"
    ondc_provider_id: str = "artisan-collective-001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
