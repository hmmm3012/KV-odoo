#!/usr/bin/env python3
"""Stdlib HTTPS reverse proxy in front of local Odoo.

Used when Docker/nginx cannot bind :443 (no root / docker socket). Default listen
is :8443 so it does not collide with a later nginx TLS container on :443.
"""
from __future__ import annotations

import http.client
import http.server
import os
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "proxy-connection",
}


def _split_host_port(value, default_port):
    parsed = urlsplit("http://" + value if "://" not in value else value)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port
    return host, port


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 720

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {}
        for key, value in self.headers.items():
            if key.lower() in HOP_BY_HOP:
                continue
            headers[key] = value
        headers["X-Forwarded-Proto"] = "https"
        headers["X-Forwarded-For"] = self.client_address[0]
        headers["X-Forwarded-Host"] = self.headers.get("Host", "")
        headers["Connection"] = "close"

        upstream_host, upstream_port = self.server.upstream
        conn = http.client.HTTPConnection(upstream_host, upstream_port, timeout=self.timeout)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        finally:
            conn.close()

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()


def main():
    here = Path(__file__).resolve().parent
    cert_dir = Path(os.environ.get("CERT_DIR", here.parent / "nginx" / "certs"))
    cert = cert_dir / "fullchain.pem"
    key = cert_dir / "privkey.pem"
    if not cert.is_file() or not key.is_file():
        sys.stderr.write("Missing %s or %s. Run generate-tls-cert.sh first.\n" % (cert, key))
        return 1

    listen_host, listen_port = _split_host_port(os.environ.get("HTTPS_LISTEN", "0.0.0.0:8443"), 8443)
    upstream = _split_host_port(os.environ.get("ODOO_UPSTREAM", "127.0.0.1:8069"), 8069)

    httpd = http.server.ThreadingHTTPServer((listen_host, listen_port), ProxyHandler)
    httpd.upstream = upstream
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print("HTTPS https://%s:%s → http://%s:%s" % (listen_host, listen_port, upstream[0], upstream[1]), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
