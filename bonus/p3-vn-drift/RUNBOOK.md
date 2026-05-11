# RUNBOOK — VN News Drift Detection

## Alert: `VNNewsSignificantDrift` (warning)

**What:** PSI > 0.25 trên ít nhất 1 feature. Phân phối text đã shift đáng kể.

### Triage
1. Mở dashboard → xem panel "PSI by Feature" để biết feature nào bị
2. Đọc sample headline hiện tại: `bonus/p3-vn-drift/data/current_headlines.txt`
3. So sánh với reference: `bonus/p3-vn-drift/data/reference_headlines.txt`

### By feature
| Feature | Nếu bị drift |
|---------|-------------|
| `english_word_ratio` | Keyword công nghệ mới, campaign viral → thường là organic. Nếu >5% spike trong 1 ngày: check parser. |
| `text_length` | Editorial guideline change hoặc parser cắt ngắn headline → check data pipeline. |
| `tone_mark_ratio` | **NGUY HIỂM** — có thể data bị strip dấu. Rollback pipeline ngay. |

### Action
- Seasonal drift (Tết, hè): update baseline, không cần retrain
- Structural drift (parser bug): rollback data pipeline
- Organic shift (new topics emerge): schedule model retraining

---

## Alert: `VNNewsEnglishRatioSpike` (warning)

**What:** English word ratio > 2σ above 30-day rolling baseline.

### Triage
1. Đây thường là leading indicator — NER model sẽ bắt đầu fail trên loanwords
2. Check sample: tìm các từ tiếng Anh mới xuất hiện trong headline
3. Nếu là tech event (AI Day, blockchain summit...) → expected, update supplementary vocab list
4. Nếu không rõ nguyên nhân → có thể parser đang fail trên UTF-8

---

## PSI vs KL vs KS — Reflection

Trên dataset Vietnamese news headline:

- **PSI surface được shift sớm nhất** cho `english_word_ratio` (PSI = 0.32 khi reference 3% → current 12%). PSI nhạy với tail shift và interpretable (threshold 0.1/0.25 đã được industry validate).

- **KL divergence** cũng nhạy nhưng bị asymmetric — KL(P_ref || P_cur) khác với KL(P_cur || P_ref). Khi current distribution có category mới (zero bin trong reference), KL → ∞. Hữu ích cho debugging nhưng không nên dùng làm alert chính.

- **KS test** tốt để confirm statistical significance (p < 0.01 = "shift này không phải noise") nhưng bản thân KS statistic không cho biết shift có ý nghĩa thực tế không — nó chỉ nói "có khác". Với 1000 samples, KS dễ dàng p < 0.001 ngay cả khi shift không meaningful.

**Kết luận:** Dùng PSI làm metric chính để alert (có threshold interpretable), KL làm diagnostic metric khi investigating, và KS p-value làm sanity check để tránh alert trên noise.
