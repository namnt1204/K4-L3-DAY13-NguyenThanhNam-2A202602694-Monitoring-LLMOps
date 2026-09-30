# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Latency P95 của `response_sent.latency_ms` (SLO: latency <= 3000ms cho 99.5% requests)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng phải chờ đợi lâu hơn bình thường để nhận phản hồi từ chatbot/agent.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard Latency panel để xác định thời điểm bắt đầu tăng độ trễ, so sánh P50/P95/P99 và TTFT.
  2. Lọc file `data/logs.jsonl` trong khung giờ đó, tìm các log event `response_sent` có `latency_ms > 2000ms`, trích xuất một `correlation_id` bất thường tiêu biểu.
  3. Mở Langfuse trace có cùng `correlation_id`, quan sát trace tree và so sánh thời gian của child observation `retrieval` vs `generation`.
- Mitigation tạm thời:
  - Nếu span `retrieval` bị chậm: kiểm tra tài nguyên vector store / local corpus hoặc fallback sang tài liệu mặc định.
  - Nếu span `generation` bị chậm: rollback prompt/model candidate về baseline version đã ổn định (`production` -> `v1`), hoặc giảm lưu lượng request.
- Recovery check:
  - Latency P95 giảm xuống dưới 3000ms liên tục trong 10 phút.
  - Tỷ lệ lỗi duy trì dưới 2% và SLO được bảo toàn.
- Owner: `student-2A202602694`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Error rate (tỷ lệ request thất bại trên tổng request nhận được, ngưỡng tối đa 2%)
- Điều kiện và thời gian duy trì: `error_rate_pct > 2.0%` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng nhận mã lỗi HTTP 500 hoặc thông báo lỗi hệ thống, không nhận được câu trả lời từ chatbot.
- Ba bước kiểm tra đầu tiên:
  1. Mở Errors panel trên Dashboard để xem tỷ lệ lỗi tổng thể và breakdown theo `error_type`.
  2. Lọc `data/logs.jsonl` tìm các event `request_failed`, ghi nhận `error_type`, thông báo lỗi trong `payload.detail`, và lấy một `correlation_id` bị lỗi.
  3. Mở Langfuse tìm trace có `correlation_id` tương ứng, kiểm tra xem lỗi phát sinh ở tầng root (`lab-agent-run`), `retrieval` hay `generation`.
- Mitigation tạm thời:
  - Nếu lỗi `RuntimeError("Vector store timeout")` do sự cố retrieval: kích hoạt chế độ fallback tài liệu rỗng hoặc chuyển sang bộ nhớ đệm nội bộ.
  - Nếu lỗi do LLM generate crash hoặc cấu hình prompt sai: rollback prompt label `production` về phiên bản v1 ổn định.
- Recovery check:
  - Tỷ lệ lỗi (error rate) giảm về 0% hoặc dưới 2.0% liên tục trong ít nhất 10 phút.
  - Health check endpoint `/health` trả về `ok: true`.
- Owner: `student-2A202602694`

## Alert 3

- Tên: `RetrievalDegradation`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Retrieval tool success rate (ngưỡng tối thiểu 90%)
- Điều kiện và thời gian duy trì: `retrieval_success_rate_pct < 90.0%` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Câu trả lời chatbot thiếu dữ liệu tài liệu chính xác từ kiến thức doanh nghiệp, phải dùng câu trả lời chung chung hoặc fallback.
- Ba bước kiểm tra đầu tiên:
  1. Mở Errors panel trên Dashboard, kiểm tra biểu đồ và tỷ lệ `retrieval_success_rate`.
  2. Lọc `data/logs.jsonl` tìm các event có `tool_name == "retrieval"` và `tool_success == False`, trích xuất `correlation_id`.
  3. Mở trace trên Langfuse theo `correlation_id`, kiểm tra span `retrieval` và metadata trạng thái lỗi (status_message, timeout).
- Mitigation tạm thời:
  - Tắt practice scenario timeout nếu đang test, hoặc khởi động lại vector store connector.
  - Điều chỉnh cấu hình fallback corpus để đảm bảo agent vẫn tạo câu trả lời an toàn cho người dùng.
- Recovery check:
  - Tỷ lệ `retrieval_success_rate` hồi phục lên trên 90% liên tục trong 5 phút.
  - Không còn log event `tool_success: false`.
- Owner: `student-2A202602694`
