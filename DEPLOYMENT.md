# DEPLOYMENT — Day 14 Production AI Agent

## 1. Nền tảng & Cấu hình triển khai

Project `06-lab-complete/` đã được cấu hình sẵn sàng cho cả **Railway** và **Render**:
- **Railway:** `06-lab-complete/railway.toml` (`builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`, `healthcheckPath = "/health"`).
- **Render (Blueprint):** `06-lab-complete/render.yaml` (`type: web`, `runtime: docker`, `healthCheckPath: /health`, secret `AGENT_API_KEY` và `REDIS_URL` dùng `sync: false`).
- **Port động:** `Dockerfile` sử dụng `CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]` để tự động lắng nghe theo biến `PORT` do platform cấp.

> **Trạng thái Public URL:** Chưa triển khai lên Railway/Render từ môi trường local (cần tài khoản & token Railway/Render của sinh viên để `railway login` / kết nối Blueprint và tạo Managed Redis Cloud).

## 2. Environment Variables đã cấu hình (`.env.example`)

| Biến môi trường | Mô tả | Giá trị mẫu / Mặc định |
|---|---|---|
| `PORT` | Cổng lắng nghe HTTP | `8000` (hoặc do Cloud cấp) |
| `ENVIRONMENT` | Môi trường chạy | `production` |
| `AGENT_API_KEY` | Khóa bí mật xác thực `X-API-Key` | *(cấu hình trên Cloud Secret, không commit)* |
| `REDIS_URL` | Connection string tới Managed Redis | `redis://default:<pass>@<host>:<port>/0` |
| `RATE_LIMIT_PER_MINUTE` | Giới hạn request/phút mỗi key | `10` |
| `DAILY_BUDGET_USD` | Ngân sách tối đa mỗi ngày (USD) | `1.0` |
| `MONTHLY_BUDGET_USD` | Ngân sách tối đa mỗi tháng (USD) | `10.0` |

## 3. Hướng dẫn Deploy lên Railway

```bash
npm install -g @railway/cli
cd 06-lab-complete
railway login
railway init
# Tạo Redis service trên Railway Dashboard và copy REDIS_URL
railway variables set AGENT_API_KEY=<your-secret-key> REDIS_URL=<your-redis-url> ENVIRONMENT=production
railway up
railway domain
```

## 4. Các lệnh kiểm tra sau khi Deploy

Đặt `BASE=https://<your-agent-domain>`:

```bash
# 1. Health & Readiness
curl -i "$BASE/health"
curl -i "$BASE/ready"

# 2. Thiếu API Key -> 401 Unauthorized
curl -i -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'

# 3. Có API Key -> 200 OK
curl -i -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is Docker?"}'

# 4. Kiểm tra tự động bằng script chấm
python check_production_ready.py --public-url "$BASE"
```
