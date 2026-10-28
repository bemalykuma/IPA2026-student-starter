"""Part 4 student implementation."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None
        data = event.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            return None
        if data.get("personId") == self.bot_person_id:
            return None
        message = self.client.get_message(data["id"])
        if message.get("personId") == self.bot_person_id:
            return None
        room_id = message.get("roomId")
        mentioned = message.get("mentionedPeople", [])
        files = message.get("files") or []
        if len(files) > 1:
            result = {
                "status": "error",
                "result": "multiple_attachments",
            }
        elif not files:
            result = self.processor(mentioned, None, self.bot_person_id)
        else:
            content = self.client.download_file(files[0])
            with TemporaryDirectory() as tmp:
                path = Path(tmp) / "request.yaml"
                path.write_bytes(content)
                result = self.processor(mentioned, path, self.bot_person_id)
        self.client.send_message(room_id, json.dumps(result))
        return result

def make_http_handler(submit_event):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self._send_json(404, {"status": "error", "result": "not_found"})

        def do_POST(self):
            invalid = {
                "status": "error",
                "result": "invalid_event",
            }
            if self.path != "/webhook":
                self._send_json(404, invalid)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send_json(400, invalid)
                return
            if length < 1 or length > 1_000_000:
                self._send_json(400, invalid)
                return
            try:
                body = self.rfile.read(length)
                event = json.loads(body)
            except ValueError:
                self._send_json(400, invalid)
                return
            if not isinstance(event, dict):
                self._send_json(400, invalid)
                return
            submit_event(event)
            self._send_json(200, {"status": "ok", "result": "accepted"})
    return Handler

def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", 8000))

    client = WebexClient()
    response = client.session.get(
        f"{WEBEX_API_BASE}/people/me", headers=client.headers, timeout=10
    )
    response.raise_for_status()
    bot_person_id = response.json().get("id")
    logging.info("bot personId: %s", bot_person_id)

    handler = WebexEventHandler(client, bot_person_id)

    executor = ThreadPoolExecutor(max_workers=1)

    def run(event):
        try:
            handler.handle_event(event)
        except Exception:
            logging.exception("failed to handle event")
    def submit_event(event):
        executor.submit(run, event)

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    logging.info("listening on %s:%s", host, port)
    server.serve_forever()

if __name__ == "__main__":
    main()
