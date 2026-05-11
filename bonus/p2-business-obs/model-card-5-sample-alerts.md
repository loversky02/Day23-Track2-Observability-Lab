# Model Card — 5 Sample Alerts Hệ Thống Sẽ Fire Trong Tuần

Dựa trên traffic pattern thật của quán cafe: 200-400 tin nhắn/ngày, peak 7h-9h sáng và 13h-15h chiều.

---

## Alert 1: ZaloBotDown — Thứ Ba 7:15 AM

**Trigger:** Bot container bị OOM kill trong đêm do memory leak tích lũy sau 48h uptime.
**Signal:** `up{job="zalo-bot"}` → 0, Prometheus scrape fail 3 lần liên tiếp.
**Business impact:** 45 phút không nhận đơn giờ cao điểm sáng ≈ 25-35 đơn mất.
**Alert routing:** `ZaloBotDown` → severity=critical, audience=both → Slack cho Tuấn + Zalo message cho Chị Hương.
**Resolution:** Tuấn restart container, bật `--max-memory=512m` flag. Time-to-resolve: 8 phút.

---

## Alert 2: ZaloBotHighLatency — Thứ Tư 13:30 PM

**Trigger:** OpenAI API chậm bất thường (P95 latency từ 2s → 8s) do degraded performance khu vực Southeast Asia.
**Signal:** `histogram_quantile(0.95, ...) > 5.0` trong 15 phút.
**Business impact:** Khách đợi 8-10 giây mới có phản hồi → ước tính 15% khách bỏ cuộc.
**Alert routing:** `ZaloBotHighLatency` → severity=warning, audience=dev → Slack cho Tuấn.
**Resolution:** Tuấn switch temporary sang GPT-4o-mini (nhanh hơn, rẻ hơn) cho đến khi API ổn định. Time-to-resolve: 25 phút.

---

## Alert 3: ZaloBotQualityDegradation — Thứ Năm 8:00 AM

**Trigger:** Menu mới thêm 3 món "matcha đá xay", "sữa chua nếp cẩm", "trà vải thiều" — intent parser chưa được train lại, nhầm "matcha đá xay" thành "cà phê đá xay".
**Signal:** `avg(zalo_bot_order_accuracy_score) < 0.85` trong 30 phút. GPT-judge detect "order intent mismatch" tăng từ 3% → 18%.
**Business impact:** 5 khách nhận sai món trong 1 giờ, 2 người phàn nàn trên group Zalo quán.
**Alert routing:** `ZaloBotQualityDegradation` → severity=warning, audience=dev → Slack cho Tuấn.
**Resolution:** Tuấn thêm 10 few-shot examples cho 3 món mới, deploy lại intent parser. Chị Hương tặng voucher 20% cho 5 khách bị ảnh hưởng. Time-to-resolve: 45 phút.

---

## Alert 4: ZaloBotHighErrorRate — Thứ Sáu 17:00 PM

**Trigger:** Chiều thứ Sáu traffic tăng 3× (khách đặt trước cho cuối tuần), PostgreSQL connection pool cạn (20/20 connections).
**Signal:** `sum(rate(zalo_bot_requests_total{status=~"5.."}[10m])) / sum(rate(...)) > 0.1` trong 10 phút.
**Business impact:** ~40% request bị lỗi trong 20 phút, mất ước tính 15 đơn.
**Alert routing:** `ZaloBotHighErrorRate` → severity=warning, audience=dev → Slack cho Tuấn.
**Resolution:** Tuấn tăng pool size 20→50, thêm connection pooling config vào docker-compose. Time-to-resolve: 12 phút.

---

## Alert 5: ZaloBotDown (again) + SLOSlowBurn — Chủ Nhật 22:00 PM

**Trigger:** Zalo OA access token hết hạn (refresh token bug), bot trả về 401 trên mọi request.
**Signal:** `up{job="zalo-bot"}` = 1 (container vẫn chạy) nhưng error rate = 100%. `SLOSlowBurn` fire sau 30 phút vì burn rate vượt 6×.
**Business impact:** 2 giờ không nhận đơn tối Chủ Nhật. Mất ~20 đơn.
**Alert routing:** `ZaloBotDown` → severity=critical, audience=both → cả Chị Hương và Tuấn đều nhận alert.
**Root cause:** Token refresh cron job không chạy do timezone config sai (UTC vs GMT+7).
**Resolution:** Tuấn manually refresh token, fix cron timezone. Postmortem written. Time-to-resolve: 2 giờ (do Tuấn không on-call Chủ Nhật).

---

## Tổng kết tuần

| Alert | Severity | Time-to-detect | Time-to-resolve | Đơn mất |
|-------|----------|---------------|-----------------|---------|
| BotDown (OOM) | Critical | 3 phút | 8 phút | ~30 |
| HighLatency | Warning | 15 phút | 25 phút | ~15 |
| QualityDegradation | Warning | 30 phút | 45 phút | ~10 |
| HighErrorRate (DB pool) | Warning | 10 phút | 12 phút | ~15 |
| BotDown (Token expiry) | Critical | 3 phút | 120 phút | ~20 |

**Cải tiến sau tuần này:**
1. Alert `ZaloBotQualityDegradation` cần giảm `for: 30m` → `for: 15m` (phát hiện sớm hơn)
2. Token expiry nên có alert riêng: `predict_linear(zalo_bot_requests_total{status="401"}[1h], 3600) > 0`
3. Auto-scale DB pool hoặc dùng PgBouncer
4. Tuấn cần backup on-call cho Chủ Nhật
