# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Tuấn Phong
**Ngày chạy:** 2026-11-25
**Môi trường:** WSL2 Ubuntu 26.04 (Windows 11), Python 3.12.16 (venv), Docker Desktop. Agent develop chạy local bằng `uvicorn` (1 process), mock LLM offline.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < **500** ms | p95 phản ánh trải nghiệm của 95% người dùng, bỏ qua vài spike hiếm; dễ đo và theo dõi ổn định hơn max |
| Error rate `/ask` | < **2** % | Mock LLM có ~1% lỗi upstream ngẫu nhiên; ngưỡng 2% để còn error budget cho biến động, không báo động vì 1 lỗi lẻ |
| Accuracy trên golden dataset | ≥ **80** % (mục tiêu v2 sau sửa KB: **100%**) | 80% là quality gate tối thiểu để chặn regression; bản phát hành v2 nhắm 100% trên 23 câu |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Lệnh: `python load_test.py --url http://localhost:8002 --requests 300 --concurrency <c>` (agent v2, `MOCK_SLOW_RATE` mặc định 0.03 cho mục 2.1).

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.12 | 190.5 | 218.3 | 1689.7 | 0.00% | ✅ PASS |
| 10 | 42.11 | 187.8 | 216.5 | 1677.5 | 0.33% | ✅ PASS |
| 50 | 121.22 | 195.1 | 253.9 | 1699.6 | 0.00% | ✅ PASS |
| 100 | 71.27 | 303.3 | 2566.0 | 2805.7 | 0.67% | ❌ FAIL (p95) |

**Nhận xét:** RPS **không** tăng tuyến tính mãi. Từ c=1→c=50 RPS tăng mạnh (4→42→121) vì agent async phục vụ song song. Nhưng đến c=100 RPS **tụt còn 71** và p95 vọt lên 2566ms → hệ thống **bão hoà**: agent chạy 1 process (1 event loop), khi quá nhiều request đồng thời thì chúng xếp hàng, cộng thêm ~3% request "slow" (+1.5s) làm p95/p99 bị kéo lên. Tăng concurrency quá điểm bão hoà chỉ làm latency xấu đi chứ không tăng throughput.

### 2.2 Tail latency (agent v2, c=20, 300 request)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.4 | 219.7 | 223.8 |
| 0.03 (mặc định) | 239.5 | 223.3 | 1700.7 |
| 0.1 | 295.2 | 1675.9 | 1707.4 |

**Nhận xét:** Chỉ số nhạy nhất với request chậm là **p99 rồi đến p95**, còn **avg gần như không đổi** (189→295ms). Khi slow=0.03, chỉ p99 nhảy lên 1700ms; khi slow=0.1 thì cả p95 cũng bị kéo lên 1676ms. Vì vậy **không đặt SLO theo average**: 10% request chậm 1.7s vẫn cho avg "đẹp" ~295ms trong khi 1/10 người dùng chờ gần 2 giây — chỉ p95/p99 mới phơi bày tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 56.3 | 108.8 | 114.9 |
| Tổng cost (USD) | 0.000394 | 0.000758 | 0.000801 |
| Cost / câu đúng (USD) | 0.00039375 | 0.00003607 | 0.00003482 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS |

**Những câu v2 trả lời sai ban đầu và cách sửa** (chỉ sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`, không đụng golden dataset):

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `scaling-03` (Kubernetes HPA) | `cpu`, `memory`, `custom metrics` | Thêm entry KB trigger `["kubernetes","hpa","autoscaler"]`, nội dung nói HPA scale theo CPU, memory và custom metrics |
| `security-02` (JWT vs API key) | `token`, `hết hạn`, `chữ ký` | Thêm entry KB trigger `["jwt","api key","xác thực"]`, nội dung nói JWT là token có chữ ký số và thời điểm hết hạn |

Sau khi sửa: v2 đạt **23/23 (100%)**, **0 regression** so với baseline `eval_v2.json`, `run_eval.py` thoát code **0** (`Quality gate ✅ PASS`).

**Trade-off v1 vs v2 (RAG):** v2 thêm bước retrieval nên tốn **~2× token/câu** (56→109) và latency p95 cao hơn chút (184→220ms), **tổng cost cao gần gấp đôi**. Nhưng xét **cost / câu đúng**, v2 chỉ $0.0000361 so với v1 $0.0003938 — **rẻ hơn ~10,9 lần** vì v1 trả lời sai gần hết (chi tiền cho câu sai là lãng phí). Đây là lý do nên so sánh bằng *cost/câu đúng* thay vì *cost/câu*.

### Exercise 7.3 — Quality gate trong CI (dùng exit code để chặn merge)

`run_eval.py` thoát **code 1** khi `accuracy < --min-accuracy` **hoặc** có câu regression so với `--baseline`; thoát **0** khi đạt. Một bước GitHub Actions dùng exit code này để chặn merge:

```yaml
# .github/workflows/eval.yml
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Install deps
        run: pip install -r 06-lab-complete/benchmark-observability/develop/requirements.txt
      - name: Start agent v2 (nền)
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: AGENT_VERSION=v2 PORT=8002 python app.py &
      - name: Chờ agent sẵn sàng
        run: for i in $(seq 1 30); do curl -sf http://localhost:8002/health && break; sleep 1; done
      - name: Quality gate (fail -> chặn merge)
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json
```
Nếu bước cuối thoát code 1 (accuracy tụt hoặc regression), job đỏ → branch protection chặn merge PR.

---

## 4. Observability stack (production)  — *(làm ở CP8, sau giờ lab)*

### 4.1 Screenshot
- [ ] `grafana-dashboard.png` — Grafana khi đang có tải (Golden Signals)
- [ ] `jaeger-slow-trace.png` — trace chậm (span chiếm thời gian)
- [ ] `jaeger-error-trace.png` — trace lỗi (event `exception`)
- [ ] `prometheus-alert-firing.png` — ≥ 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

### 4.3 Debug bằng trace
- `trace_id`: ...
- Tổng thời gian / span chậm nhất / dòng log cùng `trace_id`: *(CP8)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút) — *(làm ở CP8)*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

---

## 6. Kết luận (phần hiệu năng & chất lượng — CP7)

- 3 điều học được:
  1. **avg che giấu tail latency** — phải đặt SLO theo p95/p99; slow 10% không đổi avg nhưng p95 nhảy từ 220ms lên 1676ms.
  2. **Throughput có điểm bão hoà** — tăng concurrency qua điểm đó (c≈100) làm p95 xấu đi mà RPS không tăng.
  3. **So sánh phiên bản bằng *cost / câu đúng*** — v2 tốn token gấp đôi nhưng rẻ hơn ~11× mỗi câu trả lời đúng; và quality gate dựa trên eval + exit code mới chặn được regression mà metric hạ tầng không thấy.
- Lên production thật sẽ thêm: alert theo **error budget burn rate**, metric/alert ở **tầng load balancer** (bắt 504 mà agent không thấy), và **eval định kỳ trên traffic thật** để bắt lỗi chất lượng.
