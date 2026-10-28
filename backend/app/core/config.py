"""Load versioned YAML defaults with KNOWGPT_ environment overrides."""
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

class AgentConfig(BaseModel):
    """Independent role model and endpoint overrides; omitted fields inherit base settings."""
    model_config = ConfigDict(extra="forbid")
    provider: Literal["demo", "ollama", "openai"] | None = None
    model: str | None = None
    url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = Field(default=120, gt=0, le=600)

class AgentSettings(BaseModel):
    """Bounded role configuration; demo remains visibly separate from model execution."""
    model_config = ConfigDict(extra="forbid")
    max_revisions: int = Field(default=2, ge=0, le=4)
    max_model_calls: int = Field(default=9, ge=3, le=20)
    summary: AgentConfig = Field(default_factory=AgentConfig)
    extractor: AgentConfig = Field(default_factory=AgentConfig)
    reviewer: AgentConfig = Field(default_factory=AgentConfig)

class Settings(BaseSettings):
    """Validated deployment settings; environment values override YAML defaults."""
    model_config = SettingsConfigDict(env_prefix="KNOWGPT_", env_nested_delimiter="__", env_file=str(ROOT / ".env"), extra="ignore")
    app_name: str = "说话即记"
    data_dir: Path = ROOT / "data"
    llm_provider: Literal["demo", "ollama", "openai"] = "demo"
    llm_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    api_key: str = ""
    embedding_provider: Literal["hash", "sentence_transformer"] = "hash"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    confidence_threshold: float = Field(default=0.75, gt=0, le=1)
    asr_model: str = "small"
    asr_device: str = "cpu"
    max_upload_mb: int = Field(default=100, ge=1, le=1024)
    prompt_version: str = "v1"
    agents: AgentSettings = Field(default_factory=AgentSettings)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        """Environment and .env override YAML defaults passed as initial values."""
        return env_settings, dotenv_settings, init_settings, file_secret_settings

def load_settings() -> Settings:
    """Return settings from repository YAML and process environment."""
    defaults = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    return Settings(**defaults)

settings = load_settings()
