import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from tools.batch_status import Batch


def test_reports_each_step_and_failures():
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_PUT(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    b = Batch("Sheets", 2, f"http://127.0.0.1:{server.server_port}/b")
    b.step("hachi")
    b.step("rin", failed=True)
    server.shutdown()
    assert [(s["done"], s["item"], s["failed"]) for s in seen] == [(0, "", 0), (1, "hachi", 0), (2, "rin", 1)]
    assert seen[0]["name"] == "Sheets" and seen[0]["total"] == 2


def test_a_dead_or_missing_status_page_never_stops_a_batch():
    Batch("Sheets", 1, "http://127.0.0.1:9/b").step("x")
    Batch("Sheets", 1, None).step("x")
