"""
Self-test of uploads (upload.py) and of several visitors at once, through a real server.py on a free port.

Six visitors: three upload a CSV of their own (an order table, a staff table and a wide synthetic table) and answer
from the true FDs of that table; three try the study's tables and answer by a fixed hash of the question.  They first
run all at once, with their answers interleaved, then each alone; every visitor must be asked the same questions and
get the same result both times, so no session sees another's table, answers or method state.  Then the checks of a
bad upload (one column, a key with two equal rows, a ragged line) and the readiness guard of an upload.
Usage:  python test_upload.py      (uploads go to study/uploads/, tries to study/sessions/test/; both removed after)
"""
import json, os, random, shutil, socket, subprocess, sys, threading, time, urllib.request, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K

HERE = os.path.dirname(os.path.abspath(__file__))


def orders():
    rnd = random.Random(1)
    cities = [("Paris", "France"), ("Lyon", "France"), ("Rome", "Italy"), ("Milan", "Italy"), ("Berlin", "Germany")]
    prods = [("Pen", "Office", "2.5"), ("Desk", "Furniture", "120"), ("Lamp", "Furniture", "35"), ("Paper", "Office", "4")]
    custs = [(f"C{100 + i}", f"Customer {i}", *rnd.choice(cities)) for i in range(30)]
    rows = ["order_id,line,customer_id,customer_name,city,country,product,category,unit_price,quantity"]
    for o in range(1, 101):
        c = rnd.choice(custs)
        for ln in range(1, rnd.randint(1, 3) + 1):
            rows.append(",".join([f"O{1000 + o}", str(ln), *c, *rnd.choice(prods), str(rnd.randint(1, 9))]))
    fds = [(["order_id"], "customer_id"), (["customer_id"], "customer_name"), (["customer_id"], "city"),
           (["city"], "country"), (["product"], "category"), (["product"], "unit_price"),
           (["order_id", "line"], "product"), (["order_id", "line"], "quantity")]
    return "orders.csv", "\n".join(rows), ["order_id", "line"], fds


def staff():
    rnd = random.Random(2)
    depts = [(f"D{i}", f"Dept {i}", f"B{i % 3}", f"Floor {i % 4}") for i in range(6)]
    rows = ["emp_id;name;dept_id;dept_name;building;floor;salary"]
    for e in range(150):
        rows.append(";".join([f"E{e}", f"Name {rnd.randint(0, 120)}", *rnd.choice(depts), str(rnd.randint(40, 90) * 1000)]))
    fds = [(["emp_id"], "name"), (["emp_id"], "dept_id"), (["emp_id"], "salary"), (["dept_id"], "dept_name"),
           (["dept_id"], "building"), (["dept_id"], "floor"), (["dept_name"], "dept_id")]
    return "staff.csv", "\n".join(rows), [], fds


def wide():
    rnd = random.Random(3)
    rows = ["k," + ",".join(f"a{j}" for j in range(11))]
    for i in range(400):
        g = rnd.randint(0, 19)
        rows.append(",".join([str(i)] + [str((g * (j + 3)) % (5 + j)) if j < 6 else str(rnd.randint(0, 3)) for j in range(11)]))
    return "wide.csv", "\n".join(rows), ["k"], [(["k"], f"a{j}") for j in range(11)]


def closure(xs, fds):
    s = set(xs)
    while True:
        new = {r for l, r in fds if set(l) <= s} - s
        if not new:
            return s
        s |= new


class Server:
    def __init__(self):
        with socket.socket() as so:
            so.bind(("127.0.0.1", 0))
            self.port = so.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.startswith("STUDY_GITHUB")}
        env["STUDY_TRIES"] = "1"
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py"), "--port", str(self.port)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.base = f"http://127.0.0.1:{self.port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(self.base + "/healthz", timeout=2)
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("the server did not start")

    def call(self, path, body=None, form=False):
        data = None if body is None else (body.encode() if form else json.dumps(body).encode())
        ctype = "application/x-www-form-urlencoded" if form else "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": ctype} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, r.geturl(), (json.loads(r.read() or b"{}") if "json" in r.headers["Content-Type"] else None)
        except urllib.error.HTTPError as e:
            return e.code, None, json.loads(e.read() or b"{}")

    def stop(self):
        self.p.terminate()
        self.p.wait(10)


def visitor(srv, kind, arg, pause, made):
    """open a session (an upload or a try), answer until it ends, return (questions, result)"""
    if kind == "upload":
        name, text, key, fds = arg
        st, _, j = srv.call("/upload", {"name": name, "csv": text, "key": key})
        assert st == 200 and j.get("go"), (st, j)
        page = j["go"]
        made.append(page.split("/")[2])
        while True:
            _, _, m = srv.call(page + "api/meta")
            if m.get("state") != "preparing":
                break
            time.sleep(0.2)
        assert m.get("state") == "open", m
        ans = lambda q: "yes" if q["rhs"] in closure(q["lhs"], fds) else "no"
    else:
        _, url, _ = srv.call("/try", f"table={arg}", form=True)
        page = url[len(srv.base):]
        made.append(page.split("/")[2])
        srv.call(page + "api/meta")
        ans = lambda q: ("yes", "no", "no")[zlib.crc32(q["text"].encode()) % 3]
    asked = []
    _, _, q = srv.call(page + "api/question")
    while not q.get("done"):
        asked.append(q["text"])
        time.sleep(pause())
        _, _, q = srv.call(page + "api/answer", {"qid": q["qid"], "answer": ans(q), "rt_ms": 500})
    _, _, r = srv.call(page + "api/result")
    for _ in range(50):
        if r.get("done"):
            break
        time.sleep(0.2)
        _, _, r = srv.call(page + "api/result")
    keep = {k: r[k] for k in ("certified", "design", "lossless", "preserving", "nf3", "answers", "yes", "no",
                              "confirmed", "documented")}
    return asked, keep


def main():
    srv = Server()
    made = []
    people = [("upload", orders()), ("upload", staff()), ("upload", wide()), ("try", 1), ("try", 2), ("try", 3)]
    try:
        together = [None] * len(people)
        rnd = random.Random(7)
        waits = [[rnd.uniform(0, 0.03) for _ in range(400)] for _ in people]

        def run(i):
            w = iter(waits[i])
            together[i] = visitor(srv, *people[i], lambda: next(w, 0), made)
        threads = [threading.Thread(target=run, args=(i,)) for i in range(len(people))]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        print(f"together: {len(people)} visitors in {time.time() - t0:.1f}s, "
              + ", ".join(f"{len(a)} questions" for a, _ in together))
        for i, p in enumerate(people):
            alone = visitor(srv, *p, lambda: 0, made)
            assert together[i] is not None, ("a visitor failed", i)
            assert alone[0] == together[i][0], ("other questions when alone", p[0], i)
            assert alone[1] == together[i][1], ("another result when alone", p[0], i)
        print("alone: every visitor gets the same questions and the same result as together")
        o = together[0][1]
        assert o["certified"] and not o["documented"] and o["lossless"] and o["preserving"] and o["nf3"], o
        keys = sorted(tuple(d["key"]) for d in o["design"])
        assert keys == [("city",), ("customer_id",), ("order_id",), ("order_id", "line"), ("product",)], keys
        print("orders.csv: certified, the textbook design", keys)
        dept = [d for d in together[1][1]["design"] if "dept_name" in d["key"] + d["other"] and "emp_id" not in d["key"]]
        assert together[1][1]["certified"] and [d["unique"] for d in dept] == [[["dept_name"]]], together[1][1]["design"]
        print("staff.csv: the department schema has dept_id as its key and dept_name as a second key (UNIQUE in SQL)")
        bad = [{"name": "a.csv", "csv": "a\n1\n2\n", "key": []},
               {"name": "b.csv", "csv": "a,b\n1,x\n1,y\n2,y\n", "key": ["a"]},
               {"name": "c.csv", "csv": "a,b\n1,x\n2\n3,z\n", "key": []}]
        for b in bad:
            st, _, j = srv.call("/upload", b)
            assert st == 400 and j.get("error"), (b["name"], st, j)
        print("bad uploads: one column, a key with equal rows and a ragged line are refused with a message")
        try:                                   # the server answers 413 without reading the body and closes
            st = srv.call("/upload", {"name": "big.csv", "csv": "x" * (11 * 2 ** 20), "key": []})[0]
        except OSError:
            st = 413
        assert st in (400, 413), st
        assert srv.call("/healthz")[0] == 200
        print("an upload over 10 MB is refused, and the server goes on")
        assert srv.call("/s/UP-0000000000000000/1/api/meta")[0] == 404, "an unknown upload is not found"
        print("an unknown upload code is not found")
    finally:
        srv.stop()
        for code in made:
            if code.startswith("UP-"):
                shutil.rmtree(os.path.join(K.KIT, "uploads", code), ignore_errors=True)
            else:
                for sno in (1, 2):
                    for ds in K.RELATIONS.values():
                        f = os.path.join(K.KIT, "sessions", "test", f"{code}_s{sno}_{ds}.jsonl")
                        if os.path.exists(f):
                            os.remove(f)


if __name__ == "__main__":
    main()
