"""Webhook translator: Dev alert → Vietnamese SMS-style message for shop owner.

Receives Alertmanager webhook payload, translates technical alerts into
human-readable Vietnamese messages suitable for a non-technical business owner.

Only forwards alerts labeled audience="both" — the shop owner doesn't need
every dev alert, only the ones that directly impact revenue.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen

# ── Translation table: alertname → Vietnamese owner message ──────
TRANSLATIONS = {
    "ZaloBotDown": (
        "Chị Hương ơi, bot Zalo đang bị lỗi không trả lời khách. "
        "Mỗi 10 phút mất khoảng 5-8 đơn. Tuấn đang kiểm tra và sẽ báo chị ngay khi bot hoạt động lại."
    ),
    "ZaloBotHighErrorRate": (
        "Bot Zalo đang có lỗi cao bất thường (>10% tin nhắn bị lỗi). "
        "Có thể khách vẫn nhắn được nhưng bot phản hồi chậm/sai. Tuấn đã nhận alert và đang xử lý."
    ),
    "ZaloBotQualityDegradation": (
        "Bot đang xác nhận order không chính xác (>15% đơn xác nhận sai món). "
        "Chị kiểm tra xem có khách nào phàn nàn về sai món không ạ. Tuấn đang kiểm tra hệ thống."
    ),
}

DEFAULT_MESSAGE = (
    "Hệ thống đang có cảnh báo kỹ thuật. Tuấn đã được thông báo. "
    "Nếu quán thấy khách phàn nàn về bot, chị báo Tuấn nhé."
)

# Config — in production, these would be env vars or a config file
ZALO_OA_URL = os.getenv("ZALO_OA_WEBHOOK_URL", "http://localhost:9080/zalo-owner")
SLACK_DEV_URL = os.getenv("SLACK_DEV_WEBHOOK_URL", "http://localhost:9080/slack-dev")


def translate_alert(alert: dict) -> tuple[str, str]:
    """Return (owner_message, should_notify_owner)."""
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    alertname = labels.get("alertname", "Unknown")
    audience = labels.get("audience", "dev")

    should_notify = audience == "both"
    msg = annotations.get("owner_message") or TRANSLATIONS.get(alertname) or DEFAULT_MESSAGE

    return msg, should_notify


class AlertmanagerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body)

        alerts = payload.get("alerts", [])
        status = payload.get("status", "firing")

        owner_messages = []
        for alert in alerts:
            if alert.get("status") == status:
                msg, should_notify = translate_alert(alert)
                if should_notify:
                    owner_messages.append(msg)
                # Always log to dev for full context
                self._send_to_slack_dev(alert)

        if owner_messages:
            self._send_to_owner(owner_messages, status)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"received": len(alerts), "notified_owner": len(owner_messages)}).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"alert-translator: ok")

    def _send_to_owner(self, messages: list[str], status: str):
        """Send Vietnamese SMS-style message to shop owner via Zalo."""
        prefix = "🔴" if status == "firing" else "✅"
        combined = f"{prefix} Cà Phê Sáng Bot — {status.upper()}\n\n" + "\n---\n".join(messages)

        try:
            req = Request(
                ZALO_OA_URL,
                data=json.dumps({"text": combined}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urlopen(req, timeout=5)
            print(f"[translator] Sent owner notification: {combined[:100]}...", file=sys.stderr)
        except Exception as e:
            print(f"[translator] Failed to send owner notification: {e}", file=sys.stderr)

    def _send_to_slack_dev(self, alert: dict):
        """Forward full alert context to dev Slack channel."""
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        dev_payload = {
            "text": f"*{labels.get('alertname', 'Unknown')}* — {annotations.get('summary', '')}",
            "attachments": [
                {
                    "color": "danger" if labels.get("severity") == "critical" else "warning",
                    "fields": [
                        {"title": "Service", "value": labels.get("service", "unknown"), "short": True},
                        {"title": "Severity", "value": labels.get("severity", "unknown"), "short": True},
                        {"title": "Description", "value": annotations.get("description", ""), "short": False},
                        {"title": "Runbook", "value": annotations.get("runbook_url", ""), "short": False},
                    ],
                }
            ],
        }

        try:
            req = Request(
                SLACK_DEV_URL,
                data=json.dumps(dev_payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urlopen(req, timeout=5)
        except Exception as e:
            print(f"[translator] Failed to send dev Slack: {e}", file=sys.stderr)


if __name__ == "__main__":
    port = int(os.getenv("TRANSLATOR_PORT", "9080"))
    server = HTTPServer(("0.0.0.0", port), AlertmanagerHandler)
    print(f"[translator] Listening on :{port}", file=sys.stderr)
    server.serve_forever()
