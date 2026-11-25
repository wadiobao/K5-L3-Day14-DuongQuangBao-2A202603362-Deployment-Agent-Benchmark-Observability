# DEPLOYMENT — Day 14 Production AI Agent

## 1. Thông tin triển khai Cloud

- **Nền tảng:** Railway (`06-lab-complete/railway.toml` + `06-lab-complete/Dockerfile`)
- **Public URL:** https://ai-agent-production-2a975481.up.railway.app
- **Services trên Railway Project (`zestful-courage`):**
  - `ai-agent`: FastAPI Production AI Agent (Docker multi-stage, port động `$PORT`, healthcheck `/health`)
  - `Redis`: Managed Redis (`redis:8.2`, kết nối qua `${{Redis.REDIS_URL}}`)

## 2. Environment Variables đã cấu hình trên Railway

| Biến môi trường | Giá trị / Nguồn |
|---|---|
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | *(cấu hình trên Railway Variables — không lưu trong repo)* |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |

## 3. Lệnh kiểm tra Public URL

Đặt `BASE=https://ai-agent-production-2a975481.up.railway.app`:

```bash
# 1. Health check -> 200 OK
curl -i "$BASE/health"

# 2. Readiness check (Redis connected) -> 200 OK
curl -i "$BASE/ready"

# 3. Thiếu API Key -> 401 Unauthorized
curl -i -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'

# 4. Có API Key -> 200 OK
curl -i -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is Docker?"}'

# 5. Kiểm tra tự động bằng script chấm
cd 06-lab-complete
python check_production_ready.py --public-url "$BASE"
```

## 4. So sánh cấu hình `railway.toml` vs `render.yaml`

- **`railway.toml`:** Dùng định dạng TOML (`builder = "DOCKERFILE"`, `healthcheckPath = "/health"`), biến môi trường và secret đặt qua Railway CLI/Dashboard.
- **`render.yaml`:** Dùng định dạng YAML (`type: web`, `runtime: docker`, `healthCheckPath: /health`), khai báo sẵn `envVars` trong file với secret dùng `sync: false` để không lộ giá trị thật.
