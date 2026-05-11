# Business Case: Cà Phê Sáng — Zalo Chatbot Observability

## Ai (Who)
**Chủ quán:** Chị Hương, 34 tuổi, chủ chuỗi 3 quán "Cà Phê Sáng" ở quận Cầu Giấy, Hà Nội.
**Người bảo trì bot:** Tuấn, 26 tuổi, freelancer IT part-time, không on-call 24/7.

## Cái gì (What)
Zalo chatbot nhận order qua tin nhắn — khách gửi "2 cà phê sữa đá, 1 trà chanh" → bot xác nhận, tính tiền, gửi xuống quầy pha chế gần nhất.

Mỗi ngày ~200-400 tin nhắn, peak 7h-9h sáng và 13h-15h chiều. Một ngày tồi tệ = mất 30-50 đơn vì chatbot chết hoặc trả lời sai.

## Vì sao (Why)
Hiện tại Chị Hương chỉ biết bot "có vấn đề" khi khách gọi điện phàn nàn — thường là 1-2 tiếng sau khi bot hỏng. Không có dashboard, không có alert.

2 failure modes quan trọng nhất với chị:
1. **Bot không trả lời (down)** — khách nhắn mà không có phản hồi → mất đơn
2. **Bot trả lời sai giá hoặc sai món** — khách order "cà phê đen" được confirm "trà đào" → khách bực, bỏ đi

Metric kỹ thuật theo sau business impact:
- "Bot down" → `up{job="zalo-bot"}` == 0 hoặc HTTP 5xx rate > 10%
- "Trả lời sai" → GPT-as-judge score trên sample response < 0.85 (đo semantic similarity giữa intent detected và order confirmed)
- "Chậm" → P95 latency > 5s (khách đợi lâu = bỏ đi)

## Sample failure modes
| Failure | Business impact | Technical signal | Who gets paged |
|---------|----------------|------------------|----------------|
| Zalo webhook timeout | Mất 30 đơn/giờ sáng | `up` = 0 hoặc 5xx > 10% trong 5 phút | Tuấn (dev) + Chị Hương (SMS tóm tắt) |
| LLM hallucinates menu items | Khách nhận confirm sai món | GPT-judge quality score < 0.85 trong 30 phút | Tuấn (dev) |
| Menu update breaks intent parser | Khách order "matcha đá xay" mới bị hiểu nhầm | Intent confidence distribution shift (PSI > 0.25) | Tuấn (dev) |
| Rate limit từ Zalo API | Bot trả lời chậm 10s+ | P95 latency > 5s | Tuấn (dev) |
| Database connection pool cạn | Order không được lưu | PostgreSQL connection pool 100% + order insert failures | Tuấn (dev) |

## Kênh alert
- **Chị Hương:** Nhận SMS-style tóm tắt tiếng Việt qua Zalo (webhook translator) — chỉ khi mất đơn hàng loạt. Không nhận alert kỹ thuật.
- **Tuấn:** Nhận Slack alert đầy đủ context + runbook link — mọi alert kỹ thuật.
