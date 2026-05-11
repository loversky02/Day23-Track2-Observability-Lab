# Bonus Reflection — 5 Provocations Complete

## Tôi ngạc nhiên cái gì?

**Điều ngạc nhiên nhất: Silent failure là failure mode đáng sợ nhất, và hầu hết default monitoring không bắt được nó.**

Khi làm Provocation 5 (chaos + postmortem), tôi cố tình inject 3 failure mode khác loại: kill service (infra), poison data (quality), inject latency (dependency). Cả 3 đều được phát hiện — nhưng cách phát hiện rất khác nhau:

- **Service down:** 2 phút. `up{}` == 0. Đơn giản, đáng tin cậy. Mọi monitoring system đều có.
- **Latency spike:** 6 phút. P99 histogram. Cũng chuẩn, nhưng investigation bị misled vì latency nằm ở telemetry pipeline chứ không phải app.
- **Quality poisoning:** 10 phút 30 giây. Và chỉ được phát hiện vì tôi đã setup `InferenceQualityDrop` alert từ trước. **Không có quality-in-loop metric, incident này invisible.** Service vẫn up, latency bình thường, error rate cao nhưng không ai biết model output là rác.

Điều này khẳng định một nguyên lý SRE mà trước đây tôi chỉ đọc trong sách: **RED metrics (Rate, Errors, Duration) là cần nhưng chưa đủ cho AI systems.** AI system cần thêm quality metric (eval-as-metric, GPT-as-judge, embedding drift) như một first-class pillar ngang hàng với 3 pillars truyền thống.

**Điều ngạc nhiên thứ hai: Dashboard cho business owner và dashboard cho dev khác nhau triệt để.**

Provocation 2 (Zalo chatbot cho quán cafe) dạy tôi rằng chủ quán không cần biết P99 latency hay error budget. Họ cần 4 con số to: bot có online không, hôm nay bao nhiêu đơn, doanh thu ước tính, bot có nhanh không. Dịch alert kỹ thuật thành 1 câu tiếng Việt ("Chị Hương ơi, bot đang lỗi, Tuấn đang sửa") là tính năng quan trọng nhất với họ — không phải PromQL query tối ưu.

**Điều ngạc nhiên thứ ba: PSI > KL > KS cho drift detection trên text.**

Khi làm Provocation 3, tôi expect KL divergence sẽ surface drift sớm nhất. Nhưng trên dataset Vietnamese news headline, PSI với threshold 0.1/0.25 đã được industry validate từ lâu (ngành ngân hàng, credit scoring) — và nó thực sự interpretable hơn KL. `english_word_ratio` có PSI = 0.32 (significant) ngay khi tỉ lệ từ tiếng Anh tăng từ 3% → 12% — đây là con số mà data scientist có thể hiểu và action ngay. "KL = 0.47" không nói lên điều gì nếu không có context.

---

## Nếu có thêm 8 giờ nữa, tôi sẽ build cái gì?

**1. Tích hợp thật tất cả 5 provocations vào 1 stack chạy được.**

Hiện tại mỗi provocation là 1 folder riêng với code + config. Bước tiếp theo là docker-compose tất cả lại: vector store service (P1) + Zalo bot simulator (P2) + drift pipeline cron (P3) + cost tracker middleware (P4) — tất cả cùng emit metrics vào Prometheus, tất cả cùng hiển thị trên 1 Grafana instance. Một `make bonus-up` duy nhất khởi động toàn bộ.

**2. PhoBERT embedding drift detection thật.**

Provocation 3 hiện dùng synthetic data với feature extraction thủ công (text length, tone marks, English ratio). Với 8 giờ, tôi sẽ tích hợp PhoBERT (via `transformers`) để extract 768-dim embeddings từ headline thật (crawl VnExpress RSS mỗi ngày), rồi compute Euclidean distance giữa reference centroid và current centroid. Đây mới là cách production team detect drift trên text — PSI trên scalar features là proxy, embedding distance là ground truth.

**3. Multi-provider cost tracking với real API calls.**

Provocation 4 hiện có pricing table cho 12 models nhưng chưa gọi API thật. Với 8 giờ, tôi sẽ build 1 middleware FastAPI đứng giữa app và OpenAI/Anthropic API, intercept mọi request, count token thật từ response (không estimate), tính cost chính xác đến 6 decimal places, và emit metrics với label `user_id` + `endpoint` + `model`. Cộng thêm rate limiter: nếu 1 user burn > $50/ngày → tự động throttle.

**4. Automated chaos testing pipeline.**

Provocation 5 là manual chaos. Với 8 giờ, tôi sẽ build Chaos Mesh hoặc ít nhất 1 cron job chạy 3 chaos scripts luân phiên mỗi tuần, tự động đo TTD/TTM, so sánh với baseline tuần trước, và generate postmortem draft tự động từ template. Mục tiêu: mỗi thứ Ba 3 AM, system tự phá mình, tự detect, tự report — và SRE chỉ review postmortem vào sáng hôm sau.

**5. Real Zalo Bot integration.**

Provocation 2 hiện là simulation. Với 8 giờ + Zalo OA API access, tôi sẽ deploy bot thật cho 1 quán cafe, instrument nó với cùng stack Prometheus + Grafana, và quan sát 1 tuần traffic thật. Đây sẽ là portfolio piece mạnh nhất: "Tôi instrument 1 Zalo chatbot thật cho 1 business Việt, đây là dashboard, đây là alert, đây là postmortem sau 1 tuần."

---

## Tổng kết

5 provocations × 4-8 giờ mỗi cái — tôi đã build được foundation cho tất cả. Mỗi cái có 1 artifact shippable: code, dashboard JSON, alert rule, runbook. Không cái nào là "tô màu vào dashboard lab" — tất cả đều trả lời 1 câu hỏi cụ thể cho 1 người cụ thể:

| Provocation | Câu hỏi | Cho ai |
|-------------|---------|--------|
| P1 | Vector store của tôi 3 tháng sau còn chạy không? | Chính tôi, 3 tháng sau |
| P2 | Bot Zalo có đang mất đơn cho chị Hương không? | Chị Hương (chủ quán) + Tuấn (dev) |
| P3 | Data news tiếng Việt hôm nay có khác tuần trước không? | Data scientist team |
| P4 | Hôm qua AI tốn bao nhiêu? Có vượt budget không? | Founder tiết kiệm |
| P5 | Nếu system hỏng, tôi biết trong bao lâu? Tôi sửa trong bao lâu? | Tôi-trong-tương-lai, on-call |
