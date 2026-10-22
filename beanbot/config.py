"""环境变量配置；缺失必填项在启动时报告。"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" .env中出现未定义的字段时忽略
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    ledger_root: Path = Path("data/ledgers")
    jwt_secret: SecretStr = Field(min_length=32)
    invite_code: SecretStr
    llm_base_url: str
    llm_api_key: SecretStr
    llm_model: str
    embedding_enabled: bool = False
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = Field(default=20, ge=1, le=512)
    # 置信度默认值
    confidence_threshold: float = Field(default=0.80, ge=0, le=1)
    clarification_candidate_limit: int = Field(default=12, ge=1, le=100)
    intent_threshold: float = Field(default=0.6, ge=0, le=1)
    ledger_cache_size: int = Field(default=64, ge=1)
    conversation_title_max_length: int = Field(default=40, ge=1, le=200)
    conversation_title_auto_length: int = Field(default=10, ge=1, le=200)
    ledger_context_lines: int = Field(default=5, ge=0, le=50)
    ledger_history_limit: int = Field(default=10, ge=1, le=100)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.sqlite"
