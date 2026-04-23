#!/usr/bin/env python3
"""Render startup wrapper.

Bind the service port immediately so Render recognizes the web process,
run Django migrations on the same container, then hand off to gunicorn.
This keeps the sqlite-backed preview usable without delaying port binding.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
import threading


class _StartupHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self._send_response()

    def do_HEAD(self):
        self._send_response(head_only=True)

    def _send_response(self, head_only: bool = False):
        body = b'CMS Aegis is starting up.\n'
        self.send_response(503)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> int:
    port = int(os.environ.get('PORT', '10000'))
    server = _ReusableTCPServer(('0.0.0.0', port), _StartupHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        migrate = subprocess.run(
            [sys.executable, 'manage.py', 'migrate', '--noinput'],
            check=False,
        )
        if migrate.returncode != 0:
            return migrate.returncode
    finally:
        server.shutdown()
        server.server_close()

    os.execvp(
        'gunicorn',
        [
            'gunicorn',
            'config.wsgi:application',
            '--bind',
            f'0.0.0.0:{port}',
        ],
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
