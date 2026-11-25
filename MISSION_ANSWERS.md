# MISSION ANSWERS — Day 14: Deployment, Agent Benchmark & Observability

**Họ tên:** Dương Quang Bảo (`2A202603362`)

---

## Part 1 — Localhost vs Production (`01-localhost-vs-production/`)

### 1. Ít nhất 5 anti-pattern trong `develop/app.py`

1. **Hard-code secret trong source code (`develop/app.py` lines 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` bị ghi trực tiếp trong code. Khi push lên GitHub, secret sẽ bị lộ ngay lập tức.
2. **Không có Config Management (`develop/app.py` lines 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` được gán cứng, không đọc từ biến môi trường nên không thể thay đổi giữa `dev`, `staging`, `production` mà không sửa code.
3. **Dùng `print()` thay cho Structured Logging và log cả secret (`develop/app.py` lines 33–34):** `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó parse cho hệ thống thu thập log (Loki/Datadog), vừa làm lộ API key ra stdout/log aggregator.
4. **Thiếu Health Check & Readiness Endpoint:** Không có `GET /health` hay `GET /ready`, khiến Docker/Kubernetes/Railway/Render không biết process còn sống hay đã sẵn sàng nhận traffic.
5. **Bind `host="localhost"`, cố định `port=8000` và bật `reload=True` (`develop/app.py` lines 51–53):** `localhost` chỉ nhận kết nối nội bộ (không truy cập được từ ngoài container), port cứng không nhận biến `$PORT` từ cloud platform, và `reload=True` gây tốn CPU/memory, không an toàn ở production.

### 2. Bảng so sánh Develop vs Production

| Tiêu chí | `develop/app.py` | `production/app.py` | Lý do quan trọng |
|---|---|---|---|
| **Cấu hình & Secret** | Hard-code trong code | Đọc từ Environment Variables (`config.py`) | Bảo mật, tuân thủ 12-Factor App, đổi config không cần sửa code |
| **Logging** | `print()` plain text, lộ secret | Structured JSON logging (`logging` + `json.dumps`), không log secret | Dễ lọc/tìm kiếm trong log aggregator, tránh rò rỉ thông tin nhạy cảm |
| **Health & Readiness** | Không có | Có `GET /health` và `GET /ready` | Platform tự động restart container lỗi và ngừng route traffic khi chưa sẵn sàng |
| **Lifecycle / Shutdown** | Không xử lý | Dùng `lifespan` của FastAPI | Đóng kết nối sạch sẽ, hoàn tất request đang chạy khi nhận `SIGTERM` |
| **Network & Port** | `host="localhost"`, `port=8000`, `reload=True` | `0.0.0.0`, port từ `$PORT`, tắt reload | Chạy được trong container và nhận port động từ Railway/Render/Cloud Run |
| **CORS** | Không cấu hình | `CORSMiddleware` giới hạn `allowed_origins` | Ngăn chặn truy cập trái phép từ domain lạ |

---

## Part 2 — Docker (`02-docker/`)

### 1. Kích thước Docker Image thực tế

Build từ thư mục gốc repository:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

| Image | Dockerfile | Kích thước thực tế |
|---|---|---|
| `my-agent:develop` | `02-docker/develop/Dockerfile` (single-stage `python:3.11`) | **1.15 GB** (`1150 MB`) |
| `my-agent:advanced` | `02-docker/production/Dockerfile` (multi-stage `python:3.11-slim`) | **163 MB** |

**Phần trăm giảm kích thước:**
$$\text{Reduction} = \frac{1150 - 163}{1150} \times 100\% \approx \mathbf{85.8\%}$$

### 2. Giải thích kỹ thuật tối ưu Docker

- **Multi-stage build:** Stage `builder` cài đặt dependencies, stage `runtime` chỉ copy thư viện đã cài và source code, loại bỏ compiler/build tools và cache pip.
- **Base image gọn (`python:3.11-slim`):** Nhỏ hơn rất nhiều so với `python:3.11` đầy đủ, giảm bề mặt tấn công (attack surface).
- **Non-root user (`appuser`):** Giảm thiểu rủi ro leo thang đặc quyền nếu ứng dụng trong container bị khai thác.
- **Layer order:** Copy `requirements.txt` và `pip install` trước khi `COPY` source code để tận dụng Docker build cache khi chỉ sửa code.
- **`.dockerignore`:** Loại bỏ `.env`, `__pycache__/`, `venv/`, `.git/` để không làm phình build context và không lộ secret vào image.

---

## Part 3 — Cloud Deployment (`03-cloud-deployment/`)

### 1. So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
|---|---|---|
| **Định dạng** | TOML | YAML |
| **Xác định build** | `[build]` với `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` | `runtime: docker` dưới mỗi service |
| **Health check** | `[deploy]` với `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| **Quản lý biến môi trường** | Thiết lập qua Railway Dashboard hoặc `railway variables set` | Khai báo trực tiếp `envVars` trong file; secret dùng `sync: false` hoặc `generateValue: true` |
| **Restart policy** | `restartPolicyType = "ON_FAILURE"` | Tự động quản lý bởi Render |

### 2. Giải thích pipeline CI/CD của Cloud Run (`cloudbuild.yaml` & `service.yaml`)

- **`cloudbuild.yaml`** định nghĩa pipeline 4 bước chạy tuần tự trên Google Cloud Build khi có commit lên `main`:
  1. `test`: Dùng `python:3.11-slim` cài dependencies và chạy `pytest tests/`.
  2. `build`: Build Docker image từ `Dockerfile`, gắn tag `$COMMIT_SHA` và `latest`, tận dụng `--cache-from`.
  3. `push`: Đẩy image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
  4. `deploy`: Gọi `gcloud run deploy` triển khai image mới lên Cloud Run (`asia-southeast1`), cấu hình `min-instances=1` (tránh cold start), `max-instances=10`, và inject secret từ Google Secret Manager (`--set-secrets`).
- **`service.yaml`** mô tả cấu hình hạ tầng dạng IaC (Knative `Service`): giới hạn tài nguyên (`cpu: "1"`, `memory: 512Mi`), `containerConcurrency: 80`, lấy secret qua `secretKeyRef`, và cấu hình `livenessProbe` (`/health`) cùng `startupProbe` (`/ready`).

---

## Part 4 — API Gateway & Security (`04-api-gateway/`)

### 1. Các lớp bảo vệ API

| Lớp bảo vệ | Cơ chế hoạt động | HTTP Status khi vi phạm |
|---|---|---|
| **API Key Auth** | Kiểm tra header `X-API-Key` so sánh constant-time (`hmac.compare_digest`) với `AGENT_API_KEY` | `401 Unauthorized` |
| **JWT Auth** | Client đăng nhập tại `POST /auth/token` để nhận JWT có chữ ký và thời hạn (`exp`), gửi qua `Authorization: Bearer <token>` | `401 Unauthorized` |
| **Rate Limiting** | Sliding window 60 giây theo API key / user lưu trên Redis Sorted Set (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE`) | `429 Too Many Requests` (kèm `Retry-After`) |
| **Cost Guard** | Cộng dồn chi phí LLM theo token (`input_tokens`, `output_tokens`) vào Redis; kiểm tra trước mỗi lần gọi LLM | `402 Payment Required` |

### 2. Phân biệt Rate Limit và Cost Guard

- **Rate Limit** giới hạn **tần suất request** (ví dụ: tối đa 10 requests/phút) để chống spam/DDoS và bảo vệ tài nguyên server.
- **Cost Guard** giới hạn **tổng chi phí tiền tệ (USD)** tiêu thụ bởi LLM dựa trên số lượng token thực tế (ví dụ: `DAILY_BUDGET_USD=1.0`), bảo vệ ngân sách ngay cả khi số lượng request ít nhưng mỗi prompt/response rất dài.

---

## Part 5 — Scaling & Reliability (`05-scaling-reliability/`)

### 1. Health Check (`/health`) vs Readiness (`/ready`)

- **`GET /health` (Liveness Probe):** Kiểm tra process ứng dụng còn sống hay không. Luôn trả `200 OK` kể cả khi Redis bị ngắt kết nối (tránh bị orchestrator restart oan gây crash loop).
- **`GET /ready` (Readiness Probe):** Kiểm tra service đã sẵn sàng phục vụ traffic hay chưa bằng cách ping Redis (`redis_healthy()`). Nếu Redis mất kết nối, trả `503 Service Unavailable` để Load Balancer tạm ngừng gửi traffic tới instance đó.

### 2. Kiến trúc Stateless với Redis

- Khi chạy nhiều instance (ví dụ `--scale agent=3` sau Nginx Load Balancer), nếu lưu bộ đếm Rate Limit, Cost Guard hoặc lịch sử hội thoại trong RAM của từng process Python thì các request tiếp theo đi sang instance khác sẽ bị mất state.
- Đưa toàn bộ shared state vào **Redis** giúp mọi instance dùng chung dữ liệu và giữ nguyên trạng thái kể cả khi agent restart.

### 3. Graceful Shutdown

- Khi container nhận tín hiệu `SIGTERM` (lúc deploy bản mới hoặc scale down), `uvicorn` (chạy ở PID 1 qua `exec`) ngừng nhận kết nối mới, hoàn tất các request đang xử lý (in-flight), rồi chạy phần dọn dẹp trong `lifespan` (ghi log shutdown, đóng kết nối Redis) và thoát với `exit code 0` trong < 10 giây.

---

## Part 6 — Final Project: Production-ready Agent (`06-lab-complete/`)

Đã hoàn thiện toàn bộ các module và file cấu hình trong `06-lab-complete/`:
- `app/config.py`: Đọc cấu hình 12-Factor từ env (`PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD`).
- `app/auth.py`: Xác thực `X-API-Key` bằng `hmac.compare_digest` (trả `401`).
- `app/redis_client.py`: Kết nối Redis lazy, cung cấp `redis_healthy()` cho `/ready` (`200` / `503`).
- `app/rate_limiter.py`: Sliding window 60s bằng Redis Sorted Set (trả `429` + `Retry-After`).
- `app/cost_guard.py`: Theo dõi chi phí token theo ngày trong Redis (trả `402` khi vượt budget).
- `app/main.py`: `/health`, `/ready`, `/ask`, structured JSON logging (`JsonFormatter`), `lifespan` shutdown, global exception handler không lộ stack trace.
- `Dockerfile`: Multi-stage `python:3.11-slim`, user non-root `appuser`, `HEALTHCHECK`, `exec uvicorn ... --port ${PORT:-8000}`, dung lượng image **160 MB**.
- `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`.

### Kết quả kiểm tra `python check_production_ready.py`

- **Tổng số check đạt:** **42/42 checks passed** (11/12 tiêu chí ✅ trên Windows; tiêu chí 11 *Graceful shutdown* phần Docker `docker stop` đạt ✅ `exit code 0, 0.9s`, chỉ phần gửi `SIGTERM` trực tiếp tới process Windows báo ⚠️ do hạn chế của `os.name == "nt"` trên Windows).
- Chi tiết:
  - Docker build thành công (42s), kích thước **160 MB** (< 500 MB), `/health` → 200.
  - `docker-compose.yml` có `agent` + `redis` với `REDIS_URL` + `depends_on`.
  - `/health` → 200; `/ready` → 200 (khi có Redis) và 503 (khi mất Redis).
  - Thiếu/sai `X-API-Key` → 401; đúng key → 200.
  - Vượt `RATE_LIMIT_PER_MINUTE=5` → 429; restart agent vẫn giữ 429 (stateless Redis).
  - Vượt `DAILY_BUDGET_USD=0.000001` → 402.
  - Log ứng dụng xuất chuẩn JSON hợp lệ (12 dòng JSON).
  - `docker stop` tắt êm với exit code 0 trong 0.9s.
