# Day 14 Lab — Mission Answers

> Học viên: Nguyễn Tuấn Phong · MSSV: 2A202603712 · Lớp: K5-L3A
> Repo bài làm cá nhân cho Day 14 — Deployment, Benchmark & Observability.

---

## CP0 — Setup môi trường

- **OS làm bài:** WSL2 Ubuntu 26.04 LTS (bắt buộc để CP5 test SIGTERM/graceful shutdown; kiểm tra `python -c "import os; print(os.name)"` → `posix`).
- **Python:** cài bằng `uv` (binary tải về user-dir, không `sudo`): CPython 3.12.16 trong venv `~/day14venv`. Lý do không dùng Python 3.14 mặc định của distro: `pydantic==2.9.0` / `psutil` chưa có wheel sẵn cho 3.14.
- **Docker:** Docker Desktop 29.9.3 + Compose v5.7.0 (chạy qua WSL integration).
- **Self-check CP0:** `docker run --rm hello-world` → *(điền kết quả sau khi bật WSL integration cho distro Ubuntu)*.

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

### Exercise 2.1 — Đọc Dockerfile (4 câu hỏi)

<!-- CP2 -->

### Exercise 2.2 — Gọi container

<!-- CP2 -->

### Exercise 2.3 — So sánh kích thước image (số đo thật)

<!-- CP2: develop MB, production MB, % chênh lệch (docker images) -->

### Exercise 2.4 — Stack docker-compose + Nginx

<!-- CP2: sơ đồ service + kết quả test qua Nginx -->

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
