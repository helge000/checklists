#!/usr/bin/env python3
"""
Deploy webhook — listens for GitHub push events, runs git pull,
then restarts the checklist container via the Docker socket.

Environment:
    WEBHOOK_SECRET   GitHub webhook secret (required)

Usage:
    python3 webhook.py          # listens on 0.0.0.0:9000
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SECRET      = os.environ.get("WEBHOOK_SECRET", "").encode()
REPO_DIR    = Path(__file__).parent.parent
DEPLOY_SH   = REPO_DIR / "deploy/deploy.sh"


def _verify(secret: bytes, body: bytes, sig_header: str) -> bool:
    if not secret:
        return True   # no secret configured → allow all (not recommended)
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def _deploy():
    if DEPLOY_SH.exists():
        log.info("Running %s", DEPLOY_SH)
        result = subprocess.run(
            ["bash", str(DEPLOY_SH)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.error("deploy.sh failed:\n%s", result.stderr)
        else:
            log.info("deploy.sh OK:\n%s", result.stdout.strip())
    else:
        # Fallback: plain git pull
        log.info("No deploy.sh found — running git pull")
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "origin", "main"],
                       timeout=60)


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Simple health-check endpoint."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        if not _verify(SECRET, body, self.headers.get("X-Hub-Signature-256", "")):
            log.warning("Invalid signature from %s", self.client_address)
            self.send_response(403)
            self.end_headers()
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")
            return

        if event == "push":
            try:
                payload = json.loads(body)
                ref     = payload.get("ref", "")
                log.info("Push event on %s", ref)
            except Exception:
                pass
            _deploy()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt, *args):  # suppress default access log
        pass


if __name__ == "__main__":
    host, port = "0.0.0.0", 9000
    log.info("Webhook listener on %s:%d", host, port)
    log.info("Repo dir: %s", REPO_DIR)
    log.info("Secret configured: %s", bool(SECRET))
    HTTPServer((host, port), Handler).serve_forever()
