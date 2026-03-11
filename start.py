#!/usr/bin/env python3
"""Wrapper that runs bot.py + a tiny HTTP health server for Render free tier."""
import threading, os
from http.server import HTTPServer, BaseHTTPRequestHandler

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"HWS Physio Bot OK")
    def log_message(self, *a): pass

def run_health():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()

threading.Thread(target=run_health, daemon=True).start()

# Now run the actual bot
import bot
bot.main()
