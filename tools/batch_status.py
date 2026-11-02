"""Tells AI Lab how far a long batch has got. Best effort: a batch never stops over this."""

import json
import os
import urllib.request

DEFAULT_URL = "http://192.168.10.19:8080/designs/api/batch"


def batch_url() -> str:
    return os.environ.get("NIGHTWIRE_BATCH_URL", DEFAULT_URL)


class Batch:
    """`url=None` reports nothing, which is what tests and offline runs use."""

    def __init__(self, name: str, total: int, url: str | None):
        self.name, self.total, self.url = name[:80], total, url
        self.done = self.failed = 0
        self._send("")

    def step(self, item: str = "", failed: bool = False) -> None:
        self.done += 1
        self.failed += bool(failed)
        self._send(item)

    def _send(self, item: str) -> None:
        if not self.url:
            return
        body = {"name": self.name, "done": self.done, "total": self.total, "item": item[:80], "failed": self.failed}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="PUT",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=3).close()
        except OSError:
            pass
