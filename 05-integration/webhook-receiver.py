"""Local webhook receiver — captures Alertmanager Slack-formatted POSTs.

Starts an HTTP server on :9080 that logs every POST body to a JSONL file
and pretty-prints it on a clean HTML page for screenshot capture.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

RECEIVED: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": ts, "path": self.path, "headers": dict(self.headers), "body": body}
        RECEIVED.append(entry)
        # Append to JSONL
        with open("/tmp/webhook-log.jsonl", "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        # Render a clean HTML page showing latest webhook payloads
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Slack Webhook Receiver</title>
<style>
body{font-family:monospace;max-width:900px;margin:20px auto;background:#1a1a2e;color:#e0e0e0}
h1{color:#36a64f}.card{background:#16213e;border:1px solid #0f3460;border-radius:8px;padding:16px;margin:12px 0}
pre{background:#0f0f23;padding:12px;border-radius:4px;overflow-x:auto;white-space:pre-wrap}
.ts{color:#888;font-size:0.85em}.label{color:#f39c12}.empty{color:#888;text-align:center;margin:40px}
</style></head><body>
<h1>&#x1f7e2; Alertmanager → Slack Webhook Receiver</h1>
<p>Listening on :9080. POSTs from Alertmanager appear below.</p>
"""
        if not RECEIVED:
            html += '<div class="empty">No webhook payloads received yet. Waiting for Alertmanager to send...</div>'
        for e in reversed(RECEIVED[-10:]):
            try:
                parsed = json.loads(e["body"]) if e["body"].startswith("{") else e["body"]
            except Exception:
                parsed = e["body"]
            body_str = json.dumps(parsed, indent=2, ensure_ascii=False) if isinstance(parsed, dict) else str(parsed)
            html += f'<div class="card"><div class="ts">{e["timestamp"]}</div><pre>{body_str}</pre></div>'
        html += "</body></html>"
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, fmt, *args):
        pass  # quiet


def main():
    port = int(os.getenv("WEBHOOK_PORT", "9080"))
    srv = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Webhook receiver listening on :{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
