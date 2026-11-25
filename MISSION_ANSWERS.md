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

### Exercise 4.1–4.3 — Kết quả test (401 / 200 / 429)

<!-- CP3: output curl -i, che token -->

### Exercise 4.4 — Cost guard

<!-- CP3: giải thích cách làm -->

---

## Part 5 — Scaling & Reliability

### Exercise 5.1–5.5 — Ghi chú & kết quả test

<!-- CP4 -->

---

## Part 6 — Final Project: Output check_production_ready.py

<!-- CP5: dán phần "📋 Checklist Deliverable" của output PASS 12/12 -->

---

## AI log

> Theo [RULES.md](RULES.md) mục 1: mỗi lần dùng AI cho code Part 6 hoặc câu trả lời — ghi hỏi gì, nhận gì, tự sửa/tự kiểm tra thế nào.

- **CP0 (setup):** Dùng AI trợ lý (Claude Code) để dựng môi trường WSL: cài `uv`, tạo venv Python 3.12, cài `requirements.txt`. Tự kiểm tra: chạy `uv pip`, import `fastapi/pydantic/redis/jwt/psutil` thành công, xác nhận `os.name == posix`.
- **CP1 (Part 1 answers):** Hỏi AI cách đọc anti-pattern trong `develop/app.py` và đối chiếu với `production/`. Tự kiểm tra: tự chạy bản develop bằng `uvicorn`, curl `/`, `/ask?question=`, `/ask` JSON (422) và `/health` (404); số liệu/HTTP code trong bài là output mình chạy được.
- **CP2 (Part 2 answers):** Hỏi AI cách đọc Dockerfile multi-stage và compose. Tự kiểm tra: tự build 2 image và đo `docker images` (develop 1.67 GB, advanced 240 MB), tự chạy container develop + stack compose và curl qua Nginx; mọi con số MB là số mình đo, không chép từ README.
