# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.txt`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Thành Nam
- **MSSV:** 2A202602694
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/namnt1204/K4-L3-DAY13-NguyenThanhNam-2A202602694-Monitoring-LLMOps.git
- **Commit SHA cuối:** `61a34f8` (hoặc SHA commit cuối khi hoàn tất nộp bài)
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602694`

## 2. Evidence index

| Evidence | File Ảnh (Screenshot) | File Dữ liệu / Text |
|---|---|---|
| 01. Pytest cuối | [evidence/01-pytest.png](evidence/01-pytest.png) | [evidence/01-pytest.txt](evidence/01-pytest.txt) |
| 02. Log validator | [evidence/02-log-validator.png](evidence/02-log-validator.png) | [evidence/02-log-validator.txt](evidence/02-log-validator.txt) |
| 03. Dashboard validator | [evidence/03-dashboard-validator.png](evidence/03-dashboard-validator.png) | [evidence/03-dashboard-validator.txt](evidence/03-dashboard-validator.txt) |
| 04. Structured log | [evidence/04-structured-log.png](evidence/04-structured-log.png) | [evidence/04-structured-log.json](evidence/04-structured-log.json) |
| 05. PII redaction | [evidence/05-pii-redaction.png](evidence/05-pii-redaction.png) | [evidence/05-pii-redaction.txt](evidence/05-pii-redaction.txt) |
| 06. Trace list | [evidence/06-trace-list.png](evidence/06-trace-list.png) | [evidence/06-trace-list.txt](evidence/06-trace-list.txt) |
| 07. Trace waterfall | [evidence/07-trace-waterfall.png](evidence/07-trace-waterfall.png) | [evidence/07-trace-waterfall.txt](evidence/07-trace-waterfall.txt) |
| 08. Trace metadata | [evidence/08-trace-metadata.png](evidence/08-trace-metadata.png) ([08b](evidence/08b-trace-metadata.png)) | [evidence/08-trace-metadata.txt](evidence/08-trace-metadata.txt) |
| 09. Prompt versions | [evidence/09-prompt-versions.png](evidence/09-prompt-versions.png) | [evidence/09-prompt-versions.txt](evidence/09-prompt-versions.txt) |
| 10. Prompt rollback | [evidence/10-prompt-rollback.png](evidence/10-prompt-rollback.png) | [evidence/10-prompt-rollback.txt](evidence/10-prompt-rollback.txt) |
| 11. Dashboard runtime | [evidence/11-dashboard-overview.png](evidence/11-dashboard-overview.png) | [evidence/11-dashboard-overview.txt](evidence/11-dashboard-overview.txt) |
| 12. Incident metric | [evidence/12-incident-metric.png](evidence/12-incident-metric.png) | [evidence/12-incident-metric.txt](evidence/12-incident-metric.txt) |
| 13. Incident log | [evidence/13-incident-log.png](evidence/13-incident-log.png) | [evidence/13-incident-log.txt](evidence/13-incident-log.txt) |
| 14. Incident trace | [evidence/14-incident-trace.png](evidence/14-incident-trace.png) | [evidence/14-incident-trace.txt](evidence/14-incident-trace.txt) |


## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đạt 4/4 tiêu chí (Schema, Correlation ID, Enrichment, PII Scrubbing) |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Hợp lệ 100% contract YAML với đủ threshold, unit, aggregation |
| `pytest` | 22 passed | 27 passed | 27/27 passed bao gồm test PII CCCD, thẻ ngân hàng, tracing adapter |
| Số traces hợp lệ | 0 traces | 26+ traces | Tất cả traces sinh ra trong project Langfuse cá nhân `day13-k4-l3b-2A202602694` |
| Số PII leak | 0 | 0 | Không còn bất kỳ rò rỉ Email, SĐT VN, CCCD, Thẻ ngân hàng nào trong logs |
| Latency P95 / TTFT P95 | ~1200ms / 50ms | 1,164.3ms / 50ms | Đạt SLO an toàn (SLO <= 3000ms) |
| Retrieval success rate | 100% | 100% (bình thường) | Hoạt động ổn định, ghi nhận chính xác khi có sự cố |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
  - Trong `app/middleware.py`, `CorrelationIdMiddleware` kiểm tra header `x-request-id`. Nếu hợp lệ theo regex `^req-[0-9a-fA-F]{8}$`, giữ nguyên mã đã chuẩn hóa chữ thường. Nếu thiếu hoặc không hợp lệ, sinh mới bằng `f"req-{secrets.token_hex(4)}"`.
  - Correlation ID được bind vào `structlog.contextvars` ngay sau khi `clear_contextvars()` được gọi đầu request để ngăn rò rỉ ngữ cảnh giữa các request.
  - Correlation ID được lưu vào `request.state.correlation_id` và gán vào header phản hồi `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:**
  - Đầu request (`request_received`): `service="api"`, `correlation_id`, `user_id_hash` (băm SHA256 12 ký tự), `session_id`, `feature`, `model`, `env`, và `payload.message_preview` đã scrub PII.
  - Cuối request (`response_sent`): bổ sung `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`, và `payload.answer_preview`.
- **Cách bảo đảm PII được scrub trước khi ghi:**
  - Hàm `scrub_event` trong `app/logging_config.py` được đăng ký trong danh sách processors của Structlog ngay trước `JsonlFileProcessor()` và `JSONRenderer()`.
  - Bộ khử PII duyệt đệ quy toàn bộ cấu trúc event (strings, dicts lồng nhau, lists, tuples) và thay thế các pattern nhạy cảm theo thứ tự ưu tiên: Credit Card (`\b(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}|\d{16})\b`), CCCD 12 số (`\b\d{12}\b`), Số điện thoại Việt Nam, và Email.
- **Cách kiểm chứng kết quả:**
  - Chạy `validate_logs.py` đạt điểm tuyệt đối 100/100, xác nhận 0 PII leak và 100% log records có đủ metadata.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
  - Cấu hình API keys riêng từ project `day13-k4-l3b-2A202602694` trên Langfuse Cloud vào `.env`. Mọi traces và observation đều mang `projectId: cmunhnfoh0iddad0c7iu6rhih` và `environment: dev`.
- **Cấu trúc root/retrieval/generation observations:**
  - Trace cấp cao nhất: `day13-agent-request`.
  - Root observation: `lab-agent-run` (type: `AGENT`), liên kết context tags `["lab", feature, model]`.
  - Child observation 1: `retrieval` (type: `RETRIEVER`), theo dõi quá trình tra cứu vector store, `top_k`, `document_count`, `tool_success` mà không capture raw prompt/docs.
  - Child observation 2: `generation` (type: `GENERATION`), theo dõi model LLM (`claude-sonnet-4-5`), `usage_details` (input/output tokens), `cost_details`, và liên kết trực tiếp với Langfuse Prompt Object qua `prompt=prompt_obj`.
- **Cách nối trace với log:**
  - Cả structured log và root metadata của Langfuse trace đều lưu chung một `correlation_id` (ví dụ `req-1a2b3c4d`), cho phép tra cứu chéo 1:1 từ log event sang trace waterfall.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version `1`, labels: `["baseline", "production"]`.
- **Version/label candidate:** Version `2`, labels: `["candidate", "latest"]` (có thêm chỉ dẫn trả lời súc tích).
- **Trace ID của mỗi version:**
  - Version 1 (Baseline): `213d56bd3e9233cbd0d9e588f45e87cc`
  - Version 2 (Candidate): `e1e0b41cbc96732223b84fde3a5a0bf2`
- **Cách promote và rollback `production`:**
  - Sử dụng API/UI của Langfuse để di chuyển label:
    - Promote: Gán label `production` sang version 2 (`client.update_prompt(name='day13-chat', version=2, new_labels=['candidate', 'production'])`).
    - Rollback: Gán label `production` trở lại version 1 (`client.update_prompt(name='day13-chat', version=1, new_labels=['baseline', 'production'])`).
  - Ứng dụng tự động cập nhật phiên bản prompt theo nhãn mà không cần sửa đổi bất kỳ dòng mã nào.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
  - Dashboard runtime được dựng trực tiếp tại `http://127.0.0.1:8000/dashboard` và script độc lập `dashboard/app.py` với giao diện Dark Cyberpunk trực quan, auto-refresh 15 giây, hiển thị đầy đủ 6 panels theo đúng `config/dashboard.yaml`:
    1. Latency (ms): P50, P95, P99, TTFT P95 kèm đường ngưỡng P95 &le; 3000ms.
    2. Traffic (req/min): Tổng số request và tốc độ kèm đường ngưỡng rate &ge; 1 req/min.
    3. Errors (%): Tỷ lệ lỗi request và tỷ lệ thành công của retrieval kèm ngưỡng &le; 2.0%.
    4. Cost (USD): Chi phí tích lũy theo phút và tổng cửa sổ 60m kèm ngưỡng &le; $2.50.
    5. Tokens: Tổng token, tokens in, tokens out kèm ngưỡng &le; 50,000.
    6. Quality: Điểm đánh giá chất lượng trung bình kèm ngưỡng &ge; 0.75.
- **SLO và lý do chọn:**
  - Primary SLO: 99.5% requests đạt trạng thái thành công và có độ trễ &le; 3000ms trong chu kỳ 28 ngày.
  - Lý do: Baseline đo được cho thấy P95 bình thường chỉ dao động từ 400ms đến 1100ms. Ngưỡng 3000ms cung cấp hệ số an toàn gấp khoảng 3x để hấp thụ biến thiên mạng và độ trễ tự nhiên của LLM generation mà không làm gián đoạn trải nghiệm người dùng.
- **Cách tính error budget:**
  - Công thức: `allowed_bad_requests = total_requests * (1 - SLO)`.
  - Với SLO 99.5% trong 28 ngày, error budget là 0.5%.
  - Cụ thể:
    - Với 1,000 requests: cho phép tối đa 5 requests vi phạm SLO.
    - Với 10,000 requests: cho phép tối đa 50 requests vi phạm SLO.
    - Với 100,000 requests: cho phép tối đa 500 requests vi phạm SLO.
- **Ba alert và runbook tương ứng:**
  - Alert 1 (`HighLatencyP95` - warning, duration 5m, condition `p95_latency_ms > 3000`): Cảnh báo khi độ trễ P95 vượt ngưỡng 3000ms liên tục trong 5 phút. Runbook tại `docs/alerts.md#alert-1`.
  - Alert 2 (`HighErrorRate` - critical, duration 5m, condition `error_rate_pct > 2.0`): Cảnh báo khi tỷ lệ request thất bại vượt quá 2% trong 5 phút. Runbook tại `docs/alerts.md#alert-2`.
  - Alert 3 (`RetrievalDegradation` - warning, duration 5m, condition `retrieval_success_rate_pct < 90.0`): Cảnh báo khi tỷ lệ tra cứu tri thức thành công tụt dưới 90%. Runbook tại `docs/alerts.md#alert-3`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 2026-09-30 03:37:49Z – 03:38:18Z (UTC)
- **Triệu chứng từ metrics:**
  - Trên Latency panel của Dashboard (`http://127.0.0.1:8000/dashboard`), độ trễ P95 tăng vọt từ mức bình thường ~391ms lên mức 2,654ms (và spike tối đa đạt 8,710ms), vượt ngưỡng latency thử thách 2,000ms và tiến sát ngưỡng cảnh báo SLO 3,000ms.
- **Log line và correlation ID liên quan:**
  - Lọc `data/logs.jsonl` phát hiện chuỗi sự kiện `response_sent` bất thường với `correlation_id = req-2fe07040`, `session_id = k4-l3b-challenge-s01`, `feature = monitoring`, `latency_ms = 2653ms` (thời điểm `2026-09-30T03:38:07.704756Z`).
- **Trace ID và span gây ảnh hưởng:**
  - Mở Langfuse trace với `correlation_id = req-2fe07040`.
  - Phân tích waterfall cho thấy span `retrieval` (RETRIEVER) chiếm tới ~2.506s (tương đương 94.3% tổng thời gian request), trong khi span `generation` (GENERATION) chỉ mất ~0.152s.
- **Root cause:**
  - Điểm nghẽn độ trễ xuất phát hoàn toàn từ tầng truy xuất tài liệu/vector store (`retrieval` path bị trễ nhân tạo 2.5s qua kịch bản `rag_slow` kích hoạt trên feature `monitoring`), hoàn toàn không phải do LLM generation.
- **Fix action:**
  - Tắt kịch bản lỗi bằng `python scripts/inject_incident.py --disable`. Trong môi trường production thực tế: tăng scale cụm vector store, bật in-memory cache cho các câu hỏi phổ biến, hoặc chuyển sang fallback tài liệu cục bộ khi truy xuất quá 1.5s.
- **Preventive measure:**
  - Thiết lập circuit breaker và timeout 1.5s cho retriever tool; kích hoạt Alert 1 (`HighLatencyP95`) để phát hiện sớm hiện tượng suy giảm hiệu năng trước khi vi phạm SLO.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  - Quyết định phân tách biểu thức chính quy nhận diện thẻ tín dụng thành `\b(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}|\d{16})\b`. Trước đó, nếu dùng dấu phân cách tùy chọn giữa từng nhóm 4 số (`\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b`), một dãy 12 số CCCD đi kèm 4 số thẻ phía sau sẽ bị match nhầm thành một thẻ tín dụng, làm sót token CCCD. Việc yêu cầu dấu phân cách đồng nhất hoặc 16 số liền nhau đã xử lý triệt để xung đột giữa CCCD và thẻ tín dụng.
- **Một lỗi/blocker đã gặp:**
  - Lỗi `StopIteration` khi truy vấn Langfuse API ngay lập tức sau lệnh `c.flush()` trong unit script.
- **Cách tìm nguyên nhân và xử lý:**
  - Đọc tài liệu SDK của Langfuse và nhận ra rằng phương thức `flush()` chỉ đảm bảo dữ liệu đã được gửi tới gateway của Langfuse Cloud, trong khi OpenTelemetry pipeline phía server cần 5–15 giây để ingest vào cơ sở dữ liệu có thể query. Giải pháp là thêm độ trễ hợp lý hoặc kiểm tra trực tiếp qua OpenTelemetry context attributes.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics**: Cho biết *cái gì* đang xảy ra và *khi nào* (triệu chứng tổng thể: P95 tăng, error rate tăng).
  - **Logs**: Cho biết *request cụ thể nào* bị ảnh hưởng và ngữ cảnh hệ thống (trích xuất `correlation_id`, user, session, payload).
  - **Traces**: Cho biết *tại sao* và *ở bước nào* bên trong request đó (đi sâu vào waterfall: phát hiện chính xác span `retrieval` chậm chứ không phải `generation`).
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - Quản trị prompt qua version và label cho phép đội ngũ LLMOps thử nghiệm prompt mới mà không làm gián đoạn hạ tầng, đồng thời có thể tức thời rollback về phiên bản an toàn khi phát hiện suy giảm chất lượng hoặc đột biến token/chi phí. SLO và error budget đóng vai trò là "hợp đồng chất lượng" giúp cân bằng giữa tốc độ phát triển tính năng và độ ổn định hệ thống.
- **Điều quan trọng nhất đã học:**
  - Nguyên tắc thiết kế Single Source of Truth cho Correlation ID: duy nhất một ID xuyên suốt từ HTTP Header &rarr; Middleware Context &rarr; Structured Logs &rarr; Traces Metadata &rarr; Response Header.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Không có. Toàn bộ các checkpoint từ CP0 đến CP4 cùng 2 hạng mục Bonus (+10 điểm) và thử thách chính thức CP3 (`day13-k4-l3b-monitoring-llmops-v1`) đã hoàn thành và được kiểm chứng 100%.

## 8.1. Hạng mục Bonus (+10 điểm)

- **Bonus 1: Automation hữu ích (Secret/PII Scanner & CI Workflow) (+5 điểm):**
  - Đã xây dựng công cụ quét tự động [`scripts/scan_secrets_pii.py`](scripts/scan_secrets_pii.py) nhằm phát hiện sớm nguy cơ rò rỉ secret key (`sk-lf-...`), API key, và PII thô (CCCD, Credit Card, SĐT) trước khi commit.
  - Đã thiết lập pipeline GitHub Actions CI tại [`.github/workflows/ci.yml`](.github/workflows/ci.yml) để tự động hóa: cài đặt, chạy secret scan, chạy pytest và xác thực dashboard contract trên mỗi lượt push/PR.
- **Bonus 2: Audit log riêng có Schema, Retention & Truy vấn minh họa (+5 điểm):**
  - Đã triển khai module audit log tại [`app/audit.py`](app/audit.py) ghi nhận các thao tác kiểm soát hệ thống (bật/tắt incident, thay đổi cấu hình) vào `data/audit.jsonl` theo chuẩn `config/logging_schema.json`.
  - Tích hợp chính sách retention tự động (lưu trữ tối đa 1,000 sự kiện gần nhất).
  - Cung cấp công cụ dòng lệnh [`scripts/query_audit.py`](scripts/query_audit.py) hỗ trợ lọc nhật ký kiểm toán theo `event`, `actor`, `level`, và `limit`.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.

