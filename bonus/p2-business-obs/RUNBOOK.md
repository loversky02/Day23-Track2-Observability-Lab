# RUNBOOK — Zalo Bot "Cà Phê Sáng"

## Alert: `ZaloBotDown` (critical — page immediately)

**Impact:** Khách nhắn không được trả lời. Mỗi 10 phút ≈ mất 5-8 đơn.

### Triage (5 phút đầu)
1. `curl -X POST "https://openapi.zalo.me/v2.0/oa/message"` — Zalo API còn sống không?
2. Check `docker ps | grep zalo-bot` — container còn chạy không?
3. Check `docker logs zalo-bot --tail 50` — có lỗi gì không?
4. Check Zalo OA dashboard — có bị chặn / rate-limit không?

### Common causes
| Symptom | Fix |
|---------|-----|
| Container stopped | `docker restart zalo-bot` |
| Zalo webhook 401 | Refresh OA access token trong Zalo Developer Console |
| OOM kill | Tăng memory limit: `docker update --memory 512m zalo-bot` |
| Rate limit | Giảm concurrent connection, bật queue |

### Escalation (sau 15 phút)
- Gọi Zalo OA support nếu là API issue phía Zalo
- Bật backup mode: chuyển khách sang gọi điện thoại / Google Form tạm

---

## Alert: `ZaloBotHighErrorRate` (warning — 30 phút)

**Impact:** >10% request lỗi. Một số khách không order được.

### Triage
1. Phân loại lỗi: `sum(rate(zalo_bot_requests_total[5m])) by (status)`
2. 503: Server quá tải → scale up hoặc restart
3. 502: Zalo API trả lỗi → check Zalo status page
4. 504: LLM timeout → tăng timeout hoặc fallback sang template response

---

## Alert: `ZaloBotQualityDegradation` (warning — investigate)

**Impact:** Bot vẫn trả lời nhưng xác nhận sai món → khách nhận nhầm đồ.

### Triage
1. Lấy sample bị sai: `SELECT * FROM order_logs WHERE accuracy_score < 0.7 ORDER BY created_at DESC LIMIT 20`
2. Check pattern: món mới trong menu? intent bị nhầm với intent khác?
3. Nếu là món mới → cập nhật intent training data
4. Nếu là LLM hallucinate → thêm few-shot examples vào system prompt
5. Nếu drift kéo dài > 1h → rollback LLM model version
