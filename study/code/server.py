"""
The web server of the study (README, "Online"), with the standard library only.  No passwords: a participant opens the
site, enters the code the experimenter gave them and the session number, and answers; several participants can answer
at the same time.

  /                        the start page (index.html): a participant code and session 1 or 2, or "try it"
  /s/<code>/<n>/           the session's page (ui.html): instructions, two practice questions, the questions, the
                           exit questionnaire; reopening it continues the session where it is
  /s/<code>/<n>/api/...    meta, question, answer, stop, practice, questionnaire
  /s/<code>/<n>/docs/<f>   the documentation of the relation (conditions E and P only): the files in docs/<relation>/,
                           and links to the official documents listed in docs/<relation>/links.json
  POST /try                a test session of its own for anyone who wants to try (code TP0x-xxxxxx)
  /status                  for the experimenter: the state of every session (no answers), and a reset for the test
                           codes; the answers themselves are only in the private data repository
  /healthz                 for the uptime monitor (GET or HEAD)

The codes are E01-E03, P01-P03, U01-U03; TE01 ... TU03 are the experimenter's own tests and TP0x-xxxxxx the tries, not
part of the study, whose files go to sessions/test/.  Session files are kept by store.py, except those of the tries,
which stay on the instance's disk.  A try idle for IDLE seconds is ended and released, and at most MAX_TRIES are kept.
A try shows the relations of the study, so STUDY_TRIES=0 removes it before the first real session.

Locally:   python server.py [--port 8765]
On Render: render.yaml at the root of the repository; STUDY_GITHUB_REPO and STUDY_GITHUB_TOKEN set by hand for
           durable storage.
"""
import argparse, html, json, mimetypes, os, random, re, secrets, signal, sys, threading, time, traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K
import session as S
from store import Store

UI = os.path.join(K.HERE, "ui.html")
INDEX = os.path.join(K.HERE, "index.html")
DOCS = os.path.join(K.KIT, "docs")
SESSIONS = os.path.join(K.KIT, "sessions")
CODES = [c + n for c in K.CONDITIONS for n in sorted(K.ASSIGN)]
TESTS = ["T" + c for c in CODES]
IDLE, MAX_TRIES = 30 * 60, 10
LIVE, SEEN, LIVE_LOCK = {}, {}, threading.Lock()              # (code, n) -> Session, and when it was last used
CFG = {}


def canonical(code):
    """E01, TE01, TP02-1a2b3c from any letter case"""
    head, _, tail = code.partition("-")
    return head.upper() + ("-" + tail.lower() if tail else "")


def valid(code, sno):
    try:
        K.parse(code)
        return sno in (1, 2)
    except AssertionError:
        return False


def folder(code):
    return os.path.join(SESSIONS, "test") if code.startswith("T") else SESSIONS


def file_of(code, sno):
    return os.path.join(folder(code), f"{code}_s{sno}_{K.relation_of(code, sno)}.jsonl")


def is_try(code):
    return "-" in code


def session_for(code, sno):
    with LIVE_LOCK:
        s = LIVE.get((code, sno))
        if s is None:
            s = S.Session(code, sno, folder(code), live_minutes=CFG["minutes"],
                          on_write=None if is_try(code) else CFG["store"].changed)
            LIVE[(code, sno)] = s
        SEEN[(code, sno)] = time.time()
        return s


def release_tries(keep):
    """end and release the tries idle for IDLE seconds, and the oldest ones beyond keep; True if there is room"""
    with LIVE_LOCK:
        tries = sorted((SEEN[k], k) for k in LIVE if is_try(k[0]))
        now = time.time()
        drop = [k for t, k in tries if now - t > IDLE]
        rest = [(t, k) for t, k in tries if now - t <= IDLE]
        while len(rest) >= keep and rest and now - rest[0][0] > 600:  # the oldest, if it has been quiet for 10 min
            drop.append(rest.pop(0)[1])
        for k in drop:
            s = LIVE.pop(k)
            SEEN.pop(k, None)
            if not s.closed:
                s.stop("idle")
                if s.fh is not None and not s.fh.closed:
                    s.fh.close()
        return len(rest) < keep


def meta(s):
    docs = []
    if s.condition in ("E", "P"):
        d = os.path.join(DOCS, s.ds)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f == "links.json":
                    with open(os.path.join(d, f), encoding="utf-8") as fh:
                        docs += [{"name": x["name"], "href": x["url"]} for x in json.load(fh)]
                elif not f.startswith(".") and f != "README.md":
                    docs.append({"name": f, "href": "docs/" + urllib.parse.quote(f)})
    return {"session_no": s.session_no, "condition": s.condition, "relation": s.ds, "attributes": s.rel.names,
            "sample": s.rel.sample, "rows": s.rel.rows, "docs": docs, "test": s.test, **s.progress()}


def status_page():
    st = CFG["store"].state()
    warn = ("" if st["durable"] else
            "<p class=warn><b>Storage is not durable.</b> STUDY_GITHUB_REPO and STUDY_GITHUB_TOKEN are not both set, so "
            "the session files live on this instance's disk only, which Render wipes at every restart or deploy. "
            "Do not run real sessions like this.</p>")
    err = st["last_error"] or ""
    for name in filter(None, [st["repo"], (st["repo"] or "").split("/")[0]]):  # the page is public: no names
        err = err.replace(name, "<repository>")
    st_line = (f"storage: {'a private GitHub repository' if st['durable'] else 'local disk only'}; "
               f"files put {st['puts']}, last {st['last_sync'] or '-'}, waiting {st['pending']}"
               + (f"; last error {html.escape(err)}" if err else ""))
    trs = []
    for code in CODES + TESTS:
        for sno in (1, 2):
            p = file_of(code, sno)
            state = S.status(p)
            n = sum(r["event"] == "answer" for r in S.read(p)) if state != "new" else 0
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))) if state != "new" else ""
            reset = (f"<form method=post action='/status/reset' onsubmit=\"return confirm('Delete this test session?')\">"
                     f"<input type=hidden name=code value={code}><input type=hidden name=session value={sno}>"
                     f"<button>reset</button></form>" if code.startswith("T") and state != "new" else "")
            trs.append(f"<tr class={'test' if code.startswith('T') else ''}><td>{code}</td><td>{sno}</td>"
                       f"<td>{K.relation_of(code, sno)}</td><td><a href='/s/{code}/{sno}/'>/s/{code}/{sno}/</a></td>"
                       f"<td>{state}</td><td>{n}</td><td>{when}</td><td>{reset}</td></tr>")
    tries = len(os.listdir(os.path.join(SESSIONS, "test"))) if os.path.isdir(os.path.join(SESSIONS, "test")) else 0
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>Study status</title>
<style>body{{font:14px system-ui,sans-serif;margin:24px 16px;background:#fff;color:#1d2530}} table{{border-collapse:collapse}}
td,th{{border-bottom:1px solid #ddd;padding:4px 8px;text-align:left}} tr.test{{color:#777}} form{{margin:0}}
.warn{{background:#fde8e8;border:1px solid #e0a0a0;padding:8px 12px;border-radius:6px;max-width:900px}}
.wrap{{overflow-x:auto}}</style>
<h1>Rules of a table: study status</h1>{warn}<p>{st_line}</p>
<p>Each participant opens the site, enters their code and the session number (or uses the link below). Reopening a
session continues it. Codes T… are tests, not part of the study; test files so far: {tries}. The answers are not shown
here: they are in the private data repository.</p>
<div class=wrap><table><tr><th>code</th><th>session</th><th>relation</th><th>link</th><th>state</th><th>answers</th>
<th>modified</th><th></th></tr>{''.join(trs)}</table></div>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", headers=()):
        data = body if isinstance(body, bytes) else (body.encode("utf-8") if isinstance(body, str) else
                                                     json.dumps(body, ensure_ascii=False).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def redirect(self, to):
        self.send(303, b"", "text/plain", [("Location", to)])

    def page(self, path):
        with open(path, "rb") as fh:
            self.send(200, fh.read(), "text/html; charset=utf-8")

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
        return json.loads(raw or b"{}")

    def session_path(self, path):
        """(code, n, rest) of /s/<code>/<n>/<rest>, or None"""
        m = re.match(r"^/s/([A-Za-z]{1,2}[0-9]{2}(?:-[0-9A-Fa-f]{6})?)/([12])(/.*)?$", path)
        if not m:
            return None
        code, sno = canonical(m.group(1)), int(m.group(2))
        return (code, sno, m.group(3)) if valid(code, sno) else None

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception:                                       # noqa: BLE001 (logged, answered with 500, closed)
            traceback.print_exc()
            self.close_connection = True
            try:
                self.send(500, {"error": "server"})
            except Exception:                                   # noqa: BLE001
                pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            return self.send(200, b"ok", "text/plain")
        if path == "/":
            with open(INDEX, encoding="utf-8") as fh:
                page = fh.read()
            if not CFG["tries"]:
                page = re.sub(r"<!--try-->.*?<!--/try-->", "", page, flags=re.S)
            return self.send(200, page, "text/html; charset=utf-8")
        if path == "/status":
            return self.send(200, status_page(), "text/html; charset=utf-8")
        if path.rstrip("/") == "/admin":                       # the earlier address of the status page
            return self.redirect("/status")
        sp = self.session_path(path)
        if sp:
            code, sno, rest = sp
            if rest is None or f"/s/{code}/{sno}" != path[:len(f"/s/{code}/{sno}")]:
                return self.redirect(f"/s/{code}/{sno}/" + (rest or "/")[1:])
            rest = rest[1:]
            if rest == "":
                return self.page(UI)
            s = session_for(code, sno)
            if rest == "api/meta":
                return self.send(200, meta(s))
            if rest == "api/question":
                return self.send(200, s.question())
            if rest.startswith("docs/") and s.condition in ("E", "P"):
                f = os.path.join(DOCS, s.ds, os.path.basename(urllib.parse.unquote(rest[len("docs/"):])))
                if os.path.isfile(f):
                    with open(f, "rb") as fh:
                        return self.send(200, fh.read(), mimetypes.guess_type(f)[0] or "application/octet-stream")
        return self.send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        b = self.body()
        if path == "/try" and CFG["tries"]:
            if not release_tries(MAX_TRIES):
                return self.send(503, "Many people are trying the study right now. Please try again in a few minutes.",
                                 "text/plain; charset=utf-8")
            code = f"TP{random.choice(sorted(K.ASSIGN))}-{secrets.token_hex(3)}"
            return self.redirect(f"/s/{code}/1/")
        if path == "/status/reset":
            code, sno = b.get("code", ""), int(b.get("session", 0) or 0)
            if code in TESTS and sno in (1, 2):
                with LIVE_LOCK:
                    old = LIVE.pop((code, sno), None)
                    SEEN.pop((code, sno), None)
                    if old is not None and old.fh is not None and not old.fh.closed:
                        old.fh.close()
                    CFG["store"].delete(file_of(code, sno))
            return self.redirect("/status")
        sp = self.session_path(path)
        if sp and sp[2]:
            s = session_for(sp[0], sp[1])
            rest = sp[2][1:]
            if rest == "api/answer":
                if b.get("answer") not in ("yes", "no", "dk"):
                    return self.send(400, {"error": "answer"})
                rt = b.get("rt_ms")
                return self.send(200, s.answer(str(b.get("qid")), b["answer"], rt if isinstance(rt, int) else None))
            if rest == "api/stop":
                return self.send(200, s.stop("voluntary"))
            if rest == "api/practice":
                s.practice({"practice": b.get("practice"), "answer": b.get("answer")})
                return self.send(200, {"ok": True})
            if rest == "api/questionnaire":
                keep = {k: b.get(k) for k in ("familiarity", "fatigue", "confidence")}
                keep.update({k: str(b.get(k) or "")[:2000] for k in ("stop_reason", "comments")})
                s.questionnaire(keep)
                return self.send(200, {"ok": True})
        return self.send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--host", default="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    ap.add_argument("--minutes", type=float, default=S.LIVE_MINUTES)
    a = ap.parse_args()
    CFG["minutes"] = a.minutes
    CFG["tries"] = os.environ.get("STUDY_TRIES", "1") != "0"
    store = Store(SESSIONS, os.environ.get("STUDY_GITHUB_REPO"), os.environ.get("STUDY_GITHUB_TOKEN"),
                  os.environ.get("STUDY_GITHUB_BRANCH", "main"))
    CFG["store"] = store
    print("fetched", store.fetch_all(), "session files;", "durable" if store.durable else "LOCAL DISK ONLY", flush=True)
    store.start()
    for ds in K.RELATIONS.values():
        K.prebuilt(ds)                                          # read the pickles once

    def bye(*_):
        store.flush()
        os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    print(f"listening on {a.host}:{a.port}; status page /status", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        bye()


if __name__ == "__main__":
    main()
