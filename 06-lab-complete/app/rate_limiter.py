"""
Rate limiting (tiêu chí 7) — sliding window bằng Redis sorted set.

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây.
  • Vượt giới hạn → HTTP 429 kèm header Retry-After.
  • State nằm trong Redis → mọi worker/instance dùng chung và vẫn còn sau khi
    restart agent (script chấm restart agent rồi kiểm tra vẫn bị 429).
"""
import secrets
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Chặn (429) nếu `key` đã vượt RATE_LIMIT_PER_MINUTE trong 60s gần nhất."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    rkey = f"ratelimit:{key}"

    # Bỏ các request cũ ngoài cửa sổ rồi đếm số request còn lại.
    pipe = r.pipeline()
    pipe.zremrangebyscore(rkey, 0, now - WINDOW_SECONDS)
    pipe.zcard(rkey)
    _, count = pipe.execute()

    if count >= limit:
        oldest = r.zrange(rkey, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
                "retry_after_seconds": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    # Ghi nhận request hiện tại (member duy nhất để không bị trùng score).
    member = f"{now:.6f}:{secrets.token_hex(6)}"
    pipe = r.pipeline()
    pipe.zadd(rkey, {member: now})
    pipe.expire(rkey, WINDOW_SECONDS)
    pipe.execute()
