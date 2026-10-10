"""Builder trace: absolute start/end, every model call (model + one-line purpose, failures too), what was
created on Freya, every self-test. Plain text lines with a JSON payload; no keys ever."""
import datetime
import json
import os
import re
import sys
import threading

SECRET_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class Trace(object):
    def __init__(self, path=None, echo=True):
        self.path, self.echo = path, echo
        self.lock = threading.Lock()
        self.secrets = [os.environ.get(k) for k in SECRET_ENV if os.environ.get(k)]
        self.f = open(path, "a", encoding="utf-8") if path else None
        self.model_calls = 0

    def _clean(self, s):
        for sec in self.secrets:
            s = s.replace(sec, "<redacted>")
        return re.sub(r"fak_[A-Za-z0-9_\-]{6,}", "fak_<redacted>", s)

    def emit(self, kind, msg, **data):
        line = "%s %-8s %s%s" % (_now(), kind, msg, (" " + json.dumps(data, ensure_ascii=False, default=str)) if data else "")
        line = self._clean(line)
        with self.lock:
            if self.f:
                self.f.write(line + "\n")
                self.f.flush()
            if self.echo:
                print(line, flush=True)

    def start(self, **data):
        self.emit("START", "build started", **data)

    def end(self, **data):
        self.emit("END", "build finished", model_calls=self.model_calls, **data)

    def model_call(self, model, purpose, **data):
        with self.lock:
            self.model_calls += 1
        self.emit("MODEL", "%s | %s" % (model, purpose), **data)

    def created(self, what, **data):
        self.emit("CREATED", what, **data)

    def test(self, name, ok, **data):
        self.emit("TEST", "%s: %s" % (name, "PASS" if ok else "FAIL"), **data)

    def note(self, msg, **data):
        self.emit("NOTE", msg, **data)
