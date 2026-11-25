"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

- Đọc REDIS_URL từ config.
- KHÔNG ping Redis lúc import → app vẫn khởi động được khi Redis chưa sẵn sàng
  (redis.from_url tạo client lười, chưa mở kết nối).
- redis_healthy() dùng cho GET /ready: không kết nối được → False.
"""
import redis

from app.config import settings

# Client lười — chưa mở socket cho tới lần lệnh đầu tiên.
# socket_connect_timeout để /ready trả nhanh khi Redis chết.
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    retry_on_timeout=False,
)


def redis_healthy() -> bool:
    """True nếu Redis trả PONG, False nếu lỗi kết nối."""
    try:
        return bool(r.ping())
    except Exception:
        return False
