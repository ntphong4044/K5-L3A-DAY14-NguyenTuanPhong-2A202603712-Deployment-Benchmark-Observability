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

<!-- CP1: ít nhất 5 anti-pattern, kèm dòng code trong 01-localhost-vs-production/develop/app.py -->

### Exercise 1.2 — Gọi bản develop

<!-- CP1: lệnh curl + kết quả -->

### Exercise 1.3 — Bảng so sánh develop/production

<!-- CP1: bảng Feature | Develop | Production | Why Important -->

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
