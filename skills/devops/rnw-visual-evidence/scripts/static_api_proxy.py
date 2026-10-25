#!/usr/bin/env python3
"""Serve an exported Expo web bundle and proxy its backend paths to a loopback
mvp_site running with MOCK_SERVICES_MODE=true + TESTING_AUTH_BYPASS=true.

Why: on web the app uses relative URLs and the in-app bypass is disabled
(`Platform.OS === 'web' -> false`), while Metro's own proxy only targets Cloud
Run. Same-origin proxying here is what lets a static export reach a local mock
backend, with the bypass identity headers injected server-side.

HARNESS DISCLOSURE for anything captured through this: mock-at-network,
supplementary evidence — not real-auth or real-service acceptance.

usage: static_api_proxy.py <export-dir> <port> [--backend-port 8081]
                            [--user test-harness-1] [--email dev@example.com]
"""
import argparse
import http.client
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BACKEND_PREFIXES = ("/api/", "/health", "/v1/", "/frontend_v1/", "/mcp")


def make_handler(root: str, backend_port: int, user: str, email: str):
    bypass = {
        "X-Test-Bypass-Auth": "true",
        "X-Test-User-ID": user,
        "X-Test-User-Email": email,
    }

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, fmt, *args):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _proxy(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "accept-encoding")
            }
            headers.update(bypass)
            if body is not None:
                headers["Content-Length"] = str(len(body))
            conn = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=300)
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                # http.client already decoded the body; re-sending a
                # Transfer-Encoding header would corrupt it. Let connection
                # close delimit the response (HTTP/1.0 default) so SSE streams.
                if k.lower() in ("transfer-encoding", "connection", "content-length"):
                    continue
                self.send_header(k, v)
            self.end_headers()
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            conn.close()

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.startswith(BACKEND_PREFIXES) or path == "/favicon.ico":
                return self._proxy()
            if path != "/" and not os.path.exists(os.path.join(root, path.lstrip("/"))):
                self.path = "/index.html"  # SPA fallback
            return super().do_GET()

        def do_POST(self):
            return self._proxy()

        def do_PUT(self):
            return self._proxy()

        def do_DELETE(self):
            return self._proxy()

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("port", type=int)
    ap.add_argument("--backend-port", type=int, default=8081)
    ap.add_argument("--user", default=os.environ.get("DEV_USER_ID", "test-harness-1"))
    ap.add_argument("--email", default=os.environ.get("DEV_USER_EMAIL", "dev@worldarchitect.ai"))
    a = ap.parse_args()
    handler = make_handler(a.root, a.backend_port, a.user, a.email)
    print(f"serving {a.root} on 127.0.0.1:{a.port} -> backend 127.0.0.1:{a.backend_port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), handler).serve_forever()


if __name__ == "__main__":
    main()
