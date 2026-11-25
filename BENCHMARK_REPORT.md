# Benchmark & Observability Report — Day 14

**Họ tên:** Dương Quang Bảo (`2A202603362`)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + Docker Desktop 27.0.3 (Linux containers)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Đảm bảo 95% người dùng nhận phản hồi dưới 0.5 giây với `mock-llm-small` (~120–200ms base + 20ms retrieval). |
| Error rate `/ask` | `< 2.0 %` | Mock LLM có tỷ lệ lỗi upstream ngẫu nhiên ~1% (`MOCK_ERROR_RATE=0.01`); ngưỡng 2% cho phép dung sai nhẹ mà vẫn phát hiện sự cố sớm. |
| Accuracy trên golden dataset | `>= 100 %` (hoặc `>= 80 %` cho quality gate tối thiểu) | Đảm bảo Knowledge Base bao phủ đủ 23/23 câu hỏi chuẩn, không có regression khi nâng cấp. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Số liệu đo thực tế từ `reports/load_v2_c{1,10,50,100}.json` (300 requests mỗi mức):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.26 | 202.0 | 234.2 | 1700.5 | 0.67% | PASS |
| 10 | 42.31 | 197.6 | 291.5 | 1682.9 | 1.33% | PASS |
| 50 | 95.13 | 211.0 | 533.8 | 1694.1 | 1.00% | FAIL (p95 > 500ms) |
| 100 | 51.13 | 714.0 | 4713.7 | 4872.3 | 1.33% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency. Từ `c=1` lên `c=10`, RPS tăng gần tuyến tính (4.26 → 42.31 req/s) do I/O async (`asyncio.sleep`) xử lý song song tốt. Lên `c=50`, RPS đạt đỉnh 95.13 req/s nhưng p95 bắt đầu vượt 500ms (533.8ms). Đến `c=100`, event loop và socket queue trên single process bị bão hòa, khiến p50 nhảy lên 714ms, p95 lên 4713.7ms và RPS tụt xuống 51.13 req/s.

### 2.2 Tail latency (`concurrency=20`, 300 requests)

Số liệu đo thực tế từ `reports/load_v2_slow_{0,0.03,0.1}.json`:

| `MOCK_SLOW_RATE` | avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | RPS |
|---|---|---|---|---|---|
| 0 | 207.2 | 188.0 | 458.0 | 500.1 | 94.43 |
| 0.03 (mặc định) | 251.3 | 194.9 | 476.4 | 1700.0 | 58.68 |
| 0.1 | 361.1 | 197.9 | 1693.3 | 1733.3 | 45.25 |

**Nhận xét:** Chỉ số nhạy nhất với request chậm là **p99** (tăng từ 500.1ms lên 1700.0ms ngay khi `MOCK_SLOW_RATE=0.03`) và **p95** (nhảy vọt lên 1693.3ms khi `MOCK_SLOW_RATE=0.1`). Trong khi đó, `avg` chỉ tăng từ 207.2ms lên 251.3ms (ở mức 3%) và `p50` gần như không đổi (~195ms). Do đó, đặt SLO theo `average` sẽ che giấu trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Số liệu đo thực tế từ `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`:

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 56.8 | 109.1 | 112.3 |
| Tổng cost (USD) | $0.000400 | $0.000762 | $0.000779 |
| Cost / câu đúng (USD) | $0.00040000 | $0.00003627 | **$0.00003387** |
| Quality gate | FAIL | PASS | **PASS** |

**Những câu v2 trả lời sai ban đầu và cách đã sửa (`develop/utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "xác thực", "api key"], ...)` giải thích JWT có chữ ký số và thời gian hết hạn (`exp`). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "chỉ số"], ...)` giải thích HPA scale theo CPU, memory hoặc custom metrics. |

**Nhận xét trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 tốn gần gấp đôi token mỗi câu (109.1 vs 56.8) và chậm hơn một chút ở p95 (+17.4ms do bước retrieval), nhưng độ chính xác tăng từ **4.3% lên 100.0%**, giúp **cost trên mỗi câu trả lời đúng** giảm hơn **11 lần** (`$0.000400` → `$0.00003387`).

**Quality Gate trong CI/CD:**
- `eval/run_eval.py` trả về **exit code 1** nếu `accuracy < --min-accuracy` hoặc có câu bị regression so với `--baseline`. Trong GitHub Actions, thêm step `python eval/run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json` sẽ tự động chặn merge PR nếu chất lượng Agent đi xuống.

---

## 4. Observability stack (production)

### 4.1 Thí nghiệm "phá hệ thống" & Prometheus Alerts

Khi cấu hình fault injection (`MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large`) và chạy Locust 30 users (~140 giây), **cả 3 alert đều chuyển sang trạng thái `firing` đồng thời**:

| # | Thay đổi | Alert firing | Trạng thái | Ngưỡng `for` | Panel Grafana phản ánh rõ nhất |
|---|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | `firing` | `1m` | Golden Signals → Error rate (~18.5%) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | `firing` | `2m` | Latency & Traffic → p95/p99 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | `firing` | `2m` | LLM → Cost USD/giờ |
| E | `AGENT_VERSION=v1` | Không có alert | `inactive` | — | LLM → Retrieval hit ratio = 0% |

**Cách phát hiện lỗi chất lượng như Thí nghiệm E (`AGENT_VERSION=v1`) trong production:**
- Lỗi suy giảm chất lượng (tắt nhầm RAG/retrieval) không làm tăng HTTP 5xx hay latency, nên alert hạ tầng không kêu. Cần kết hợp:
  1. Chạy **eval quality gate** (`run_eval.py`) trong CI/CD trước khi deploy.
  2. Theo dõi **retrieval hit ratio** và cảnh báo khi tỷ lệ này tụt bất thường.
  3. Dùng **online evaluation** (LLM-as-judge lấy mẫu 1–5% traffic hoặc thumbs-up/down từ user).

### 4.2 Debug bằng trace (Jaeger + JSON Log)

- **Slow trace (`1982.8 ms`):**
  - `trace_id`: `03f58a8b0f69ce31aaf7222512f2252b`
  - Dòng log JSON tương ứng (`docker compose logs agent`):
```json
{"ts": "2026-11-25T09:17:51.453002+00:00", "level": "INFO", "service": "observable-agent", "instance": "790a6767be02", "event": "http_request", "trace_id": "03f58a8b0f69ce31aaf7222512f2252b", "span_id": "ef031d804695ec6b", "request_id": "4943a4c0dbe5", "method": "POST", "route": "/ask", "status": 200, "ms": 1982.8}
```
- **Error trace (`503 Service Unavailable`):**
  - `trace_id`: `701eb4fab01b4136240ee18c1525d551`
  - Dòng log JSON tương ứng:
```json
{"ts": "2026-11-25T09:09:04.723734+00:00", "level": "INFO", "service": "observable-agent", "instance": "efd46312b759", "event": "llm_error", "trace_id": "701eb4fab01b4136240ee18c1525d551", "span_id": "afe2f5ec7b9f3860", "request_id": "67a617ec181c", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu đo thực tế từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (tổng hợp `Aggregated` và `POST /ask`):

| Số instance | `POST /ask` RPS | Aggregated RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures (`/ask`) |
|---|---|---|---|---|---|---|
| 1 | 59.59 | 65.73 | 190 | 250 | 1700 | 50 / 7127 (0.70%) |
| 3 | 59.82 | 65.95 | 190 | 240 | 1700 | 79 / 7150 (1.10%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không làm tăng đáng kể RPS (~59.6 vs ~59.8 req/s) và gần như không giảm p95/p99** (250ms vs 240ms; p99 giữ nguyên 1700ms). Nguyên nhân:
1. Tác vụ trong `agent` là async I/O (`asyncio.sleep` mô phỏng gọi LLM), nên 1 container đã đủ xử lý mức tải do 100 Locust user tạo ra (~66 req/s với think time giữa các request).
2. **Nút thắt nằm ở upstream LLM latency** (`MOCK_LATENCY_MS` + `MOCK_SLOW_RATE` 1500ms tail), không phải CPU của FastAPI container.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. Latency trung bình (`avg`) che giấu tail latency; phải dùng `p95`/`p99` để đặt SLO.
  2. Eval trên golden dataset + quality gate bắt được lỗi chất lượng mà metric hạ tầng (CPU, 5xx) không nhìn thấy.
  3. 3 trụ cột Metrics (Prometheus/Grafana) + Traces (OpenTelemetry/Jaeger) + Structured Logs (`trace_id`) giúp khoanh vùng nút thắt từ tổng quan đến từng dòng log chỉ trong vài giây.
- **Nếu đưa lên production thật:** Sẽ bổ sung thêm metric `redis_operation_duration_seconds`, cảnh báo **cost anomaly** theo từng `api_key`, và **synthetic health probe** từ bên ngoài Load Balancer (để bắt lỗi 502/504 tại Nginx).
