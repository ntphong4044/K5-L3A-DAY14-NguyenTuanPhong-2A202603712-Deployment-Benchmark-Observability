"""
Production AI Agent — Part 6 Final Project.

Đạt đủ 12 tiêu chí trong README.md. Chạy:
    uvicorn app.main:app --workers 2
    python check_production_ready.py
"""
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ──────────────────────────────────────────────────────────
# Tiêu chí 10 — Structured logging: mỗi dòng log app là 1 JSON object.
# ──────────────────────────────────────────────────────────
_STD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger("agent")


# ──────────────────────────────────────────────────────────
# Tiêu chí 11 — Graceful shutdown qua lifespan: uvicorn (PID 1) tự xử lý
# SIGTERM, hoàn thành request đang chạy rồi thoát code 0. Phần dọn dẹp ở đây.
# ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"event": "startup", "env": settings.environment, "port": settings.port})
    yield
    logger.info("shutdown", extra={"event": "shutdown"})


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


# ── Tiêu chí 4: liveness — luôn 200 khi process còn chạy (kể cả Redis chết) ──
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Tiêu chí 5: readiness — 200 khi Redis OK, 503 khi Redis không kết nối được ──
@app.get("/ready")
def ready():
    if redis_healthy():
        return {"ready": True}
    raise HTTPException(status_code=503, detail="Redis not reachable")


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    # Thứ tự: auth (401) → rate limit (429) → budget (402) → gọi LLM → ghi cost
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    logger.info(
        "ask",
        extra={"event": "ask", "path": "/ask", "status": 200,
               "q_len": len(body.question), "cost_usd": round(cost, 6)},
    )
    return {"question": body.question, "answer": answer}
