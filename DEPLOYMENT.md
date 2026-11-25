# Deployment Information — Day 14

## Public URL

https://day14-agent-hgvs.onrender.com

## Platform

**Render** — Web Service chạy Docker (Root Directory = `06-lab-complete`, build từ `Dockerfile` multi-stage) + **Key Value (Redis)** free, cùng region **Singapore**. Deploy agent của Part 6 (`06-lab-complete/`), không phải app mẫu.

## Test Commands (4 lệnh tự kiểm CP6)

```bash
BASE="https://day14-agent-hgvs.onrender.com"
# Thay bằng AGENT_API_KEY đã đặt trên Render (KHÔNG ghi key vào repo)
KEY="<AGENT_API_KEY>"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # -> 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
     -H 'Content-Type: application/json' -d '{"question":"Hello"}'                       # -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
     -H 'Content-Type: application/json' -H "X-API-Key: $KEY" -d '{"question":"Hello"}'  # -> 200
```

Kết quả đã chạy (2026-11-25):

```text
GET  /health                 -> 200   {"status":"ok"}
GET  /ready                  -> 200   {"ready":true}
POST /ask  (không key)       -> 401   {"detail":"Missing or invalid API key..."}
POST /ask  (có key)          -> 200   {"question":"...","answer":"Deployment là quá trình đưa code..."}
```

## Environment Variables Set (trên Render, không ghi trong code)

| Biến | Ghi chú |
|------|---------|
| `AGENT_API_KEY` | Secret — client gửi qua header `X-API-Key` |
| `REDIS_URL` | Internal Key Value URL của service `day14-redis` (rate limit + cost guard) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `60` |
| `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` | `1.0` / `30.0` |
| `PORT` | Render tự inject; Dockerfile `CMD` đọc `$PORT` |

## Screenshots

- `screenshots/dashboard.png` — service `day14-agent` trạng thái Live trên Render
- `screenshots/running.png` — `/health` trả `{"status":"ok"}` trên trình duyệt
- `screenshots/test.png` — kết quả 4 lệnh tự kiểm (200/200/401/200)
