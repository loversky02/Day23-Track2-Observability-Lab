# Dataset Card — VN News Headline Drift Detection

## Dataset
**Nguồn:** VnExpress RSS headlines (tin-moi-nhat, kinh-doanh, the-gioi, giai-tri, phap-luat)
**Thời gian:** Reference = tháng 1/2025 (trước Tết), Current = tháng 3/2025 (sau Tết)
**Kích thước:** ~2000 headlines / period
**Định dạng:** Tiếng Việt có dấu, tiêu đề báo chí (formal Vietnamese)

## Vì sao thú vị
Tiếng Việt là ngôn ngữ tonal, đơn âm tiết, và có tính seasonality rất cao quanh các dịp lễ Tết. Một model sentiment classifier train trên data tháng 1 sẽ gặp vocabulary hoàn toàn khác vào tháng 3 — đây là drift detection problem thực tế mà nhiều team NLP Việt Nam gặp phải.

## Shift tôi expect quan sát được

| Feature | Reference (Jan 2025) | Current (Mar 2025) | Signal |
|---------|---------------------|-------------------|--------|
| Token frequency | "Tết", "xuân", "lì xì", "đào", "mai" | "du lịch", "hè", "WTT", "AI", "ChatGPT" | PSI > 0.25 |
| Topic distribution | 40% đời sống, 25% thời sự | 30% công nghệ, 20% du lịch | KL > 0.3 |
| Text length | ~18 từ trung bình | ~14 từ (shorter, punchier headlines) | KS p < 0.01 |
| Tone mark ratio | 65% words có dấu | 58% words có dấu (teencode/English creeping in) | PSI ~0.15 |
| English word % | 3% | 12% ("AI", "chatbot", "trending", "viral") | KS p < 0.001 |

## Shift nào là bình thường, shift nào là vấn đề?

**Bình thường (expected seasonality):**
- Token frequency shift quanh Tết → đây là seasonal pattern, không cần alert
- Topic distribution shift chậm theo mùa (hè → du lịch tăng)

**Vấn đề thật (model-breaking):**
- Sentence structure thay đổi đột ngột (editorial style change → model perplexity spike)
- Token frequency shift vượt 3σ so với cùng kỳ năm trước
- Embedding centroid distance vượt ngưỡng 0.3 (chuẩn hóa cosine)

## Approach
1. Fetch VnExpress RSS (hoặc dùng data synthetic realistic)
2. Extract features: token n-gram frequency, text length, tone marks, English word ratio, embedding via PhoBERT
3. Compute PSI, KL, KS cho từng feature
4. Emit Prometheus metrics qua pushgateway
5. Alert khi drift vượt seasonal baseline (so sánh với cùng kỳ năm trước, không so với tháng trước)

## Limitations
- Data synthetic dùng từ điển tiếng Việt thật + pattern realistic nhưng không phải crawl thật từ VnExpress
- PhoBERT embedding yêu cầu GPU hoặc thời gian inference lâu trên CPU
- Seasonal baseline cần ít nhất 1 năm data để calibrate
