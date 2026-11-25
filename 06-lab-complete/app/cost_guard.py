"""
Cost guard (tiêu chí 8) — cộng dồn chi phí LLM vào Redis.

  • Tổng chi phí trong ngày vượt DAILY_BUDGET_USD  → HTTP 402
  • Tổng chi phí trong tháng vượt MONTHLY_BUDGET_USD → HTTP 402
State nằm trong Redis (có TTL) nên nhiều instance cộng dồn chung.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    return "cost:daily:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _monthly_key() -> str:
    return "cost:monthly:" + datetime.now(timezone.utc).strftime("%Y-%m")


def _spent(key: str) -> float:
    try:
        return float(r.get(key) or 0.0)
    except Exception:
        return 0.0


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(402)."""
    daily = _spent(_daily_key())
    if daily >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "spent_usd": round(daily, 6),
                "budget_usd": settings.daily_budget_usd,
            },
        )
    monthly = _spent(_monthly_key())
    if monthly >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "spent_usd": round(monthly, 6),
                "budget_usd": settings.monthly_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng ngày/tháng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    dk, mk = _daily_key(), _monthly_key()
    pipe = r.pipeline()
    pipe.incrbyfloat(dk, cost)
    pipe.expire(dk, 2 * 24 * 3600)
    pipe.incrbyfloat(mk, cost)
    pipe.expire(mk, 40 * 24 * 3600)
    pipe.execute()
    return cost
