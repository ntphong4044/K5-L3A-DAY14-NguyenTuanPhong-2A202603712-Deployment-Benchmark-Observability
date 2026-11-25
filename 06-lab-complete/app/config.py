"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Tiêu chí 9: đọc PORT, ENVIRONMENT, AGENT_API_KEY, REDIS_URL,
RATE_LIMIT_PER_MINUTE, DAILY_BUDGET_USD, MONTHLY_BUDGET_USD từ env.
Không hard-code secret trong code — giá trị mặc định chỉ hợp lý cho local dev.
"""
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # Server — Railway/Render inject PORT động
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # Security — KHÔNG hard-code, luôn đọc từ env (đặt trên nền tảng)
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))

    # Redis — dùng chung cho rate limit + cost guard (stateless)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # Rate limit + budget
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
    daily_budget_usd: float = field(default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0")))
    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "30.0")))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


settings = Settings()
