"""
Self-test of store.py against a local imitation of the GitHub contents API (a PUT without the sha of an existing file
is refused with 422, with a wrong sha with 409, as GitHub does):
  sync      a session's file reaches the repository, complete lines only
  restart   a new instance with an empty disk fetches the file, the session continues, and the stored file equals
            the session answered without a break
  conflict  an instance that never saw a stored file of the same name keeps it and stores its own beside it
  offline   while GitHub cannot be reached the file stays waiting and is put once it can
  reset     a reset test session is removed from the repository
Usage:  python test_store.py
"""
import base64, hashlib, json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store as ST
import session as S
import test_session as T

FILES, BLOBS = {}, {}                                          # path -> bytes; sha -> bytes


def sha_of(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class FakeGitHub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def target(self):
        assert self.headers["Authorization"] == "Bearer t0ken"
        p = self.path.split("?")[0]
        return p.split("/contents/", 1)[1] if "/contents/" in p else None

    def do_GET(self):
        if "/git/blobs/" in self.path:
            return self.reply(200, {"content": base64.b64encode(BLOBS[self.path.rsplit("/", 1)[1]]).decode()})
        t = self.target()
        if t in FILES:
            return self.reply(200, {"sha": sha_of(FILES[t]), "content": base64.b64encode(FILES[t]).decode()})
        kids = {}
        for p in FILES:
            if p.startswith(t + "/"):
                rest = p[len(t) + 1:]
                kids[rest.split("/")[0]] = "dir" if "/" in rest else "file"
        if not kids:
            return self.reply(404, {"message": "Not Found"})
        return self.reply(200, [{"name": k, "type": v, "sha": sha_of(FILES[t + "/" + k]) if v == "file" else ""}
                                for k, v in kids.items()])

    def body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

    def do_PUT(self):
        t, b = self.target(), self.body()
        if t in FILES and "sha" not in b:
            return self.reply(422, {"message": "sha wasn't supplied"})
        if t in FILES and b["sha"] != sha_of(FILES[t]):
            return self.reply(409, {"message": "does not match"})
        data = base64.b64decode(b["content"])
        FILES[t], BLOBS[sha_of(data)] = data, data
        return self.reply(200, {"content": {"sha": sha_of(data)}})

    def do_DELETE(self):
        t, b = self.target(), self.body()
        if t not in FILES:
            return self.reply(404, {"message": "Not Found"})
        if b["sha"] != sha_of(FILES[t]):
            return self.reply(409, {"message": "does not match"})
        del FILES[t]
        return self.reply(200, {})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ST.API = f"http://127.0.0.1:{srv.server_address[1]}"
    tmp = tempfile.mkdtemp(prefix="hs_store_")
    part, sno, mode = "TE02", 1, "err"
    whole = T.norm(T.run_case(part, sno, os.path.join(tmp, "whole", "test"), mode))
    name = f"test/{part}_s{sno}_tpcds_core.jsonl"
    key = f"sessions/{name}"

    # sync: 30 answers, then the instance dies
    a = ST.Store(os.path.join(tmp, "a"), "o/r", "t0ken")
    s = S.Session(part, sno, os.path.join(a.folder, "test"), on_write=a.changed)
    T.drive(s, mode, cut=30)
    with open(s.path, "a", encoding="utf-8") as fh:            # a line half written when the instance died
        fh.write('{"event": "answer", "qid": ')
    a.flush()
    s.fh.close()
    stored = FILES[key].decode()
    assert stored.endswith("\n") and not stored.endswith('"qid": \n') and stored.count("\n") >= 30
    print("sync: the file is in the repository,", stored.count("\n"), "complete lines")

    # restart on an empty disk
    b = ST.Store(os.path.join(tmp, "b"), "o/r", "t0ken")
    assert b.fetch_all() == 1
    s = S.Session(part, sno, os.path.join(b.folder, "test"), on_write=b.changed)
    T.drive(s, mode)
    s.questionnaire({"familiarity": 3, "fatigue": 2, "confidence": 4, "stop_reason": "test"})
    b.flush()
    with open(s.path, "rb") as fh:
        assert FILES[key] == fh.read()
    stored = os.path.join(tmp, "stored.jsonl")
    with open(stored, "wb") as fh:
        fh.write(FILES[key])
    assert T.norm(stored) == whole
    print("restart: fetched, continued, and the stored session equals the one answered without a break")

    # conflict: an instance whose fetch failed starts the same session anew
    c = ST.Store(os.path.join(tmp, "c"), "o/r", "t0ken")
    s = S.Session(part, sno, os.path.join(c.folder, "test"), on_write=c.changed)
    T.drive(s, mode, cut=3)
    c.flush()
    s.fh.close()
    alt = [p for p in FILES if p.startswith(f"sessions/test/{part}_s{sno}_tpcds_core.conflict-")]
    with open(stored, "rb") as fh:
        assert FILES[key] == fh.read() and len(alt) == 1 and "already in the repository" in c.last_error
    print("conflict: the stored session is kept, the new one is stored as", alt[0].rsplit("/", 1)[1])

    # offline, then online again
    d = ST.Store(os.path.join(tmp, "d"), "o/r", "t0ken")
    s = S.Session("TU01", 1, os.path.join(d.folder, "test"), on_write=d.changed)
    T.drive(s, "exact", cut=5)
    api, ST.API = ST.API, "http://127.0.0.1:9"
    d.flush()
    assert d.state()["pending"] == 1 and d.last_error and "sessions/test/TU01_s1_ssb_customer.jsonl" not in FILES
    ST.API = api
    d.flush()
    assert d.state()["pending"] == 0 and "sessions/test/TU01_s1_ssb_customer.jsonl" in FILES
    print("offline: the file waited and was put once GitHub could be reached")

    # reset
    s.fh.close()
    d.delete(s.path)
    assert "sessions/test/TU01_s1_ssb_customer.jsonl" not in FILES and not os.path.exists(s.path)
    print("reset: removed here and in the repository")
    srv.shutdown()


if __name__ == "__main__":
    main()
