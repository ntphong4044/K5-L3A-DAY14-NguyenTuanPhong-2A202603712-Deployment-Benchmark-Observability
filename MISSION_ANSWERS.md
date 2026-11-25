# Day 14 Lab — Mission Answers

> Học viên: Nguyễn Tuấn Phong · MSSV: 2A202603712 · Lớp: K5-L3A
> Repo bài làm cá nhân cho Day 14 — Deployment, Benchmark & Observability.

---

## CP0 — Setup môi trường

- **OS làm bài:** WSL2 Ubuntu 26.04 LTS (bắt buộc để CP5 test SIGTERM/graceful shutdown; kiểm tra `python -c "import os; print(os.name)"` → `posix`).
- **Python:** cài bằng `uv` (binary tải về user-dir, không `sudo`): CPython 3.12.16 trong venv `~/day14venv`. Lý do không dùng Python 3.14 mặc định của distro: `pydantic==2.9.0` / `psutil` chưa có wheel sẵn cho 3.14.
- **Docker:** Docker Desktop 29.9.3 + Compose v5.7.0 (chạy qua WSL integration).
- **Self-check CP0:** `docker run --rm hello-world` → in "Hello from Docker! This message shows that your installation appears to be working correctly." (sau khi bật WSL integration cho distro Ubuntu trong Docker Desktop).

---

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns trong bản develop

Tìm trong `01-localhost-vs-production/develop/app.py` (số dòng kèm theo):

1. **Hardcode secret trong code** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` (dòng 17) và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` (dòng 18). Push lên GitHub là lộ key + mật khẩu DB ngay.
2. **Không có config management** — `DEBUG = True`, `MAX_TOKENS = 500` cố định trong code (dòng 21–22); muốn đổi phải sửa code và deploy lại.
3. **Dùng `print()` thay cho logging, và in cả secret ra log** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34). Vừa không parse được, vừa rò rỉ key vào log.
4. **Không có health check** — không có `/health` / `/ready` (ghi chú dòng 42–43). Agent crash thì platform không biết để restart, load balancer vẫn route traffic vào.
5. **Bind `host="localhost"` + port cứng, không đọc từ env** — dòng 51–53. `localhost` không nhận kết nối từ ngoài container; port 8000 cứng trong khi Railway/Render inject biến `PORT`.
6. **`reload=True` kiểu debug chạy luôn ở "production"** — dòng 53. Reload tốn RAM, theo dõi file, không an toàn khi chạy thật.
7. **Không xử lý graceful shutdown (SIGTERM)** — nhận tín hiệu tắt là cắt ngang request đang chạy.

### Exercise 1.2 — Gọi bản develop

Chạy (trong WSL, venv Python 3.12): `uvicorn app:app --host 127.0.0.1 --port 8000` trong `01-localhost-vs-production/develop/`.

```text
# GET /
HTTP/1.1 200 OK
{"message":"Hello! Agent is running on my machine :)"}

# POST /ask?question=What is deployment?   (develop nhận câu hỏi qua QUERY param)
HTTP/1.1 200 OK
{"answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."}

# POST /ask với JSON body  -> 422 (develop KHÔNG nhận JSON)
HTTP 422

# GET /health  -> 404 (develop KHÔNG có health check)
HTTP 404
```

Log server (stdout) — lộ secret, đúng anti-pattern #3:
```text
[DEBUG] Got question: What is deployment?
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Deployment là quá trình đưa code từ máy bạn lên server...
```

### Exercise 1.3 — Bảng so sánh develop/production

| Feature | Develop | Production | Vì sao quan trọng |
|---------|---------|------------|-------------------|
| Config | Hardcode trong code (dòng 17–22) | Đọc từ env qua `config.py` (`os.getenv`) | Đổi môi trường dev/stg/prod không phải sửa code; fail-fast nếu thiếu biến bắt buộc |
| Secret | `sk-...` hardcode + in ra log | Từ env, không log key | Tránh lộ key/mật khẩu khi push GitHub |
| Logging | `print()` lẫn lộn | JSON logging có cấu trúc | Log aggregator (Loki/Datadog) parse được, truy vết theo event |
| Health check | Không có → 404 | `/health` (liveness) + `/ready` (readiness) | Platform tự restart khi crash; LB chỉ route khi `/ready` 200 |
| Bind host | `localhost` | `0.0.0.0` | `0.0.0.0` mới nhận kết nối từ ngoài container |
| Port | Cứng `8000` | `int(os.getenv("PORT","8000"))` | Railway/Render inject `PORT` động |
| Reload | `reload=True` luôn | `reload=settings.debug` | Reload chỉ dùng khi dev; prod tắt để tiết kiệm RAM, ổn định |
| Shutdown | Không xử lý | `lifespan` + handler `SIGTERM` | Tắt container không cắt ngang request đang xử lý |
| CORS | Không | `CORSMiddleware` giới hạn origin | Chặn origin lạ gọi API |

**Tự kiểm tra (một anti-pattern develop đã bị production sửa, kèm dòng code):** develop hardcode `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` (`develop/app.py:17`); production đọc từ env: `openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))` (`production/config.py:27`).

**Cần hiểu:** hardcode secret nguy hiểm vì code đi đâu secret theo đó (git history, image, log) — lộ là mất tiền/bị lạm dụng. Health check cần để platform phát hiện agent chết mà restart và để LB không gửi traffic vào instance chưa sẵn sàng. Graceful shutdown cần để khi scale-in / deploy mới, request đang xử lý vẫn trả xong 200 thay vì bị cắt (tránh lỗi 5xx cho người dùng).

---

## Part 2 — Docker

### Exercise 2.1 — Đọc Dockerfile (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` — bản Python đầy đủ (~1 GB), gồm cả build tools.
2. **Working directory:** `/app` (`WORKDIR /app`); mọi `COPY`/`RUN` sau đó tính tương đối từ đây.
3. **Vì sao `COPY requirements.txt` trước rồi mới `COPY` code?** Để tận dụng Docker layer cache: layer `RUN pip install` chỉ bị rebuild khi `requirements.txt` đổi. Nếu copy toàn bộ code trước, mỗi lần sửa code sẽ invalidate luôn layer cài deps → build lại từ đầu, rất chậm.
4. **CMD vs ENTRYPOINT:** `CMD` đặt lệnh/tham số **mặc định**, dễ override khi `docker run <image> <lệnh khác>`. `ENTRYPOINT` cố định phần thực thi, phần CMD/CLI được **nối thêm** làm tham số. Thực hành phổ biến: `ENTRYPOINT` = binary, `CMD` = tham số mặc định. File này dùng `CMD ["python","app.py"]` (exec form → nhận tín hiệu đúng).

### Exercise 2.2 — Build & run container develop

Build từ **gốc repo** (Dockerfile `COPY` theo path tính từ root):
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d -p 8000:8000 my-agent:develop
```
Kết quả gọi container:
```text
GET /health -> {"status":"ok","uptime_seconds":0.3,"container":true}
POST /ask?question=What is Docker? -> {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
POST /ask  (JSON body) -> HTTP 422   # develop nhận câu hỏi qua query param, không nhận JSON
```

### Exercise 2.3 — Multi-stage build (`02-docker/production/Dockerfile`)

- **Stage 1 — builder** (`python:3.11-slim AS builder`): cài `gcc`, `libpq-dev`, rồi `pip install --user -r requirements.txt` vào `/root/.local`. Stage này có đủ build tools nhưng **không dùng để deploy**.
- **Stage 2 — runtime** (`python:3.11-slim AS runtime`): bắt đầu từ image slim sạch, `COPY --from=builder /root/.local ...`, tạo user non-root `appuser`, có `HEALTHCHECK`, `CMD uvicorn main:app --workers 2`.
- **Vì sao nhỏ hơn:** image cuối **không** chứa gcc/libpq-dev/pip cache/build layer — chỉ có Python runtime + site-packages cần để chạy.

### So sánh kích thước image (số đo bằng `docker images`)

| Image | Size (docker images) | Bytes (`docker image inspect`) |
|-------|---------------------:|-------------------------------:|
| `my-agent:develop` (single-stage, `python:3.11`) | **1.67 GB** | 1 667 792 323 |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | **240 MB** | 239 815 264 |

**Chênh lệch:** `(1 667 792 323 − 239 815 264) / 1 667 792 323 = 85.6%` → bản production **nhỏ hơn ~85.6%** (chỉ còn ~14.4% dung lượng bản develop). Production < 500 MB như yêu cầu.

### Exercise 2.4 — Stack docker-compose + Nginx

4 service trên cùng bridge network `internal`:

```text
                 host:80/443
                     │
            ┌────────▼─────────┐
   client ─▶│  nginx:alpine    │  reverse proxy + rate limit 10r/s
            │ (reverse proxy)  │  upstream agent_backend -> agent:8000
            └────────┬─────────┘
                     │ proxy_pass http://agent:8000
            ┌────────▼─────────┐
            │  agent (FastAPI) │  build multi-stage, PORT 8000 (không expose ra host)
            │  main:app x2 wk  │
            └───┬──────────┬───┘
      REDIS_URL │          │ QDRANT_URL
      ┌─────────▼──┐   ┌───▼──────────┐
      │ redis:7-   │   │ qdrant v1.9  │
      │ alpine     │   │ vector DB    │
      │ (cache/RL) │   │ (RAG)        │
      └────────────┘   └──────────────┘
```

- **Giao tiếp:** client → `nginx:80` → `agent:8000` (qua DNS tên service trong network nội bộ); agent gọi `redis:6379` và `qdrant:6333`. agent `depends_on` redis + qdrant (`condition: service_healthy`), nginx `depends_on` agent.
- **Khởi động:** `touch 02-docker/production/.env.local` rồi `docker compose -f 02-docker/production/docker-compose.yml -p k5-day14-docker up -d --build`. `ps` cho thấy redis/qdrant `healthy`, agent `health: starting`, nginx map `0.0.0.0:80->80`.
- **Test qua Nginx (port 80):**
```text
GET  http://localhost/health -> {"status":"ok","uptime_seconds":0.3,"version":"2.0.0","timestamp":"2026-11-25T09:40:07..."}
POST http://localhost/ask    -> {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```
Dọn stack: `docker compose -f 02-docker/production/docker-compose.yml -p k5-day14-docker down`.

**Cần hiểu:** multi-stage giảm dung lượng nhờ stage runtime bỏ hết build tools; `COPY requirements.txt` đứng trước `COPY . .` để layer cài deps được cache lại giữa các lần build.

---

## Part 3 — Cloud Deployment

### Exercise 3.1 / 3.2 — Deploy agent Part 6

<!-- CP6: URL public + screenshot -->

### So sánh railway.toml vs render.yaml

<!-- CP6 -->

### Exercise 3.3 — Cloud Run pipeline (3–5 dòng)

<!-- CP6 -->

---

## Part 4 — API Security

### Exercise 4.1 — Develop: API Key (`X-API-Key`)

Chạy: `AGENT_API_KEY=secret-key-123 uvicorn app:app` trong `04-api-gateway/develop/`.

```text
# [THIẾU KEY] POST /ask  -> 401
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# [SAI KEY] POST /ask (X-API-Key: wrong-key)  -> 403
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

# [ĐÚNG KEY] POST /ask (X-API-Key: secret-key-123)  -> 200
HTTP/1.1 200 OK
{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 4.2 — Production: lấy JWT token (`student`/`demo123`)

```text
POST /auth/token  {"username":"student","password":"demo123"}  -> 200
{"access_token":"eyJhbGciOiJI...<MASKED>","token_type":"bearer","expires_in_minutes":60,
 "hint":"Authorization: Bearer <MASKED>"}
```
(Token đã che. Tài khoản `student` giới hạn **10 req/phút**, budget $1/ngày.)

### Exercise 4.3 — Production: 401 / 200 / 429 (dùng token ở 4.2)

```text
# [KHÔNG TOKEN] POST /ask  -> 401
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# [CÓ TOKEN hợp lệ] POST /ask (Authorization: Bearer <MASKED>)  -> 200
HTTP/1.1 200 OK
{"question":"what is docker?","answer":"Container là cách đóng gói app...",
 "usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# [VÒNG LẶP] 13 request cùng token:
request #1..#9  -> HTTP 200
request #10..#13 -> HTTP 429      # chạm giới hạn 10/phút (1 request 200 trước đó + 9 = 10)

# curl -i request bị chặn -> 429 kèm Retry-After
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795599805
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4 — Cost guard

`cost_guard.py` cộng dồn chi phí LLM **theo ngày, theo user**:
- Giá quy đổi theo token: `cost = input_tokens/1000 * $0.00015 + output_tokens/1000 * $0.0006` (tham khảo gpt-4o-mini). Trong agent, token được ước lượng từ số từ của câu hỏi/câu trả lời (`len(text.split())*2`).
- `check_budget(user)` gọi **trước** khi gọi LLM: nếu tổng chi phí trong ngày của user ≥ `DAILY_BUDGET_USD` → raise **402 Payment Required**; nếu tổng chi phí toàn hệ thống ≥ global budget → 503.
- `record_usage(user, in, out)` gọi **sau** khi gọi LLM: cộng token vào bản ghi trong ngày, đồng thời cảnh báo (log) khi dùng ≥ 80% budget.
- Nhờ check trước + ghi sau, một user tiêu quá ngân sách sẽ bị chặn ở request kế tiếp thay vì để hoá đơn LLM tăng không kiểm soát.

**Cần hiểu:** rate limit bảo vệ **tốc độ** (chống spam/DoS, giữ tài nguyên cho mọi user) và trả **429**; cost guard bảo vệ **tiền** (chặn hoá đơn LLM vượt ngân sách) và trả **402**. Cần cả hai vì một user có thể gọi *trong* giới hạn tốc độ nhưng mỗi request lại tốn nhiều token → vẫn cháy ngân sách; ngược lại nhiều request rẻ cũng cần chặn bằng rate limit.

---

## Part 5 — Scaling & Reliability

### Exercise 5.1 — Health vs Readiness

- `GET /health` (**liveness**): trả 200 khi process còn sống. Platform dùng để quyết định có **restart container** không. Không phụ thuộc Redis.
- `GET /ready` (**readiness**): ping Redis; kết nối được → 200, không → **503**. Load balancer dùng để quyết định có **route traffic** vào instance không. (Thấy rõ trong `production/app.py`: `/ready` ping Redis, lỗi → `HTTPException(503)`.)

### Exercise 5.2 — Graceful shutdown

Nhận `SIGTERM` (tín hiệu orchestrator gửi khi scale-in/deploy): ngừng nhận request mới, xử lý xong request đang chạy, đóng kết nối rồi thoát code 0. Dùng `lifespan` của FastAPI cho phần dọn dẹp; nếu tự đăng ký signal handler thì vẫn phải để uvicorn hoàn tất tắt. (Chi tiết đầy đủ sẽ làm ở CP5 và được `check_production_ready.py` kiểm bằng cách gửi SIGTERM lúc đang có request.)

### Exercise 5.3 — Stateless design

- **Anti-pattern:** giữ state trong RAM (`conversation_history = {}`); mỗi instance có vùng nhớ riêng → scale ra nhiều instance thì request rơi vào instance khác sẽ **không thấy** history.
- **Đúng:** lưu state trong Redis (`save_session`/`load_session` dùng `setex`/`get`). Mọi instance đọc chung Redis nên session liên tục.

### Exercise 5.4 — Load balancing (scale agent=3)

```bash
cd 05-scaling-reliability/production
docker compose -p k5-day14-scaling up -d --build --scale agent=3   # stack mở cổng 8080, endpoint POST /chat
```
`docker compose -p k5-day14-scaling ps` → 3 service `agent`, 1 `nginx`, 1 `redis (healthy)`. Nginx round-robin upstream `agent:8000` qua DNS của Docker.

### Exercise 5.5 — Test stateless (`python test_stateless.py`)

```text
Session ID: 00e0f4bb-5f9e-4ed6-9fba-91d75d44bbb5
Request 1: [instance-fc8677]  Q: What is Docker?
Request 2: [instance-c3f834]  Q: Why do we need containers?
Request 3: [instance-4204a5]  Q: What is Kubernetes?
Request 4: [instance-fc8677]  Q: How does load balancing work?
Request 5: [instance-c3f834]  Q: What is Redis used for?
Instances used: {instance-fc8677, instance-4204a5, instance-c3f834}   # 3 instance khác nhau
--- Conversation History --- Total messages: 10   (5 user + 5 assistant)
✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** 5 request trong **cùng một session** rơi vào **3 instance khác nhau** (round-robin của Nginx), nhưng khi đọc `/chat/{session}/history` vẫn đủ **10 message**. Chứng tỏ state nằm trong **Redis dùng chung**, không nằm trong RAM của từng instance — đúng tính chất stateless, scale ngang không mất dữ liệu. Dọn stack: `docker compose -p k5-day14-scaling down`.

**Cần hiểu:** `/health` (liveness) khác `/ready` (readiness): liveness chỉ hỏi "process còn sống?" để restart, readiness hỏi "đã kết nối được dependency (Redis) chưa?" để route traffic — một agent vừa khởi động có thể *alive* nhưng *chưa ready*. State trong RAM hỏng khi chạy nhiều instance vì mỗi instance có bộ nhớ riêng, không instance nào thấy session của instance khác → phải đẩy state ra store chung (Redis).

---

## Part 6 — Final Project: Output check_production_ready.py

<!-- CP5: dán phần "📋 Checklist Deliverable" của output PASS 12/12 -->

---

## AI log

> Theo [RULES.md](RULES.md) mục 1: mỗi lần dùng AI cho code Part 6 hoặc câu trả lời — ghi hỏi gì, nhận gì, tự sửa/tự kiểm tra thế nào.

- **CP0 (setup):** Dùng AI trợ lý (Claude Code) để dựng môi trường WSL: cài `uv`, tạo venv Python 3.12, cài `requirements.txt`. Tự kiểm tra: chạy `uv pip`, import `fastapi/pydantic/redis/jwt/psutil` thành công, xác nhận `os.name == posix`.
- **CP1 (Part 1 answers):** Hỏi AI cách đọc anti-pattern trong `develop/app.py` và đối chiếu với `production/`. Tự kiểm tra: tự chạy bản develop bằng `uvicorn`, curl `/`, `/ask?question=`, `/ask` JSON (422) và `/health` (404); số liệu/HTTP code trong bài là output mình chạy được.
- **CP2 (Part 2 answers):** Hỏi AI cách đọc Dockerfile multi-stage và compose. Tự kiểm tra: tự build 2 image và đo `docker images` (develop 1.67 GB, advanced 240 MB), tự chạy container develop + stack compose và curl qua Nginx; mọi con số MB là số mình đo, không chép từ README.
- **CP3 (Part 4 answers):** Hỏi AI cách lấy JWT token và tạo vòng lặp curl để thấy 429. Tự kiểm tra: tự chạy bản develop + production, tự lấy token `student/demo123`, tự chạy vòng 13 request và thấy 429 từ request thứ 11 (header `retry-after`). Token đã che trước khi dán.
- **CP4 (Part 5 answers):** Hỏi AI về khác biệt liveness/readiness và stateless. Tự kiểm tra: tự `docker compose up --scale agent=3` rồi chạy `test_stateless.py`, quan sát 3 instance ID thật và history 10 message; số liệu trong bài là output mình chạy.
