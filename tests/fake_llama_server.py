"""A stand-in for llama-server in the tests. It reads --port and --alias, and
answers /health and /v1/models. With --fail, it stops at once."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

arguments = sys.argv[1:]
if "--fail" in arguments:
    print("error: the model file is broken")
    sys.exit(1)
port = int(arguments[arguments.index("--port") + 1])
alias = arguments[arguments.index("--alias") + 1]
print(f"listening on {port} as {alias}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"/health": {"status": "ok"}, "/v1/models": {"data": [{"id": alias}]}}.get(self.path)
        data = json.dumps(body or {}).encode()
        self.send_response(200 if body else 404)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
