"""
Durable copies of the session files (README, "Online").  A session writes every line to the local folder at once.
When STUDY_GITHUB_REPO and STUDY_GITHUB_TOKEN are set, a background thread puts every changed file into that private
repository, under sessions/ with the same relative path, at most every SYNC seconds and once more at shutdown; only
complete lines are put.  At startup the server first fetches the repository's session files (tried again while
GitHub cannot be reached), so that a session cut off by a restart continues (session.py).  A file is never overwritten
by one this server did not write: if the repository holds a file of that name that the server never saw, the local
one is stored beside it as <name>.conflict-<time>.jsonl.  Without the two variables the files live on the local disk
only, which on Render's free plan is wiped at every restart; the admin page says so.
Standard library only (the GitHub REST API through urllib).
"""
import base64, json, os, threading, time, urllib.error, urllib.parse, urllib.request

API = os.environ.get("STUDY_GITHUB_API", "https://api.github.com")      # another value only in tests
SYNC = 10
PREFIX = "sessions"


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(*msg):
    print("store:", *(str(m).encode("ascii", "backslashreplace").decode() for m in msg), flush=True)


class Store:
    def __init__(self, folder, repo=None, token=None, branch="main"):
        self.folder, self.repo, self.token, self.branch = folder, repo, token, branch
        self.durable = bool(repo and token)
        self.sha = {}               # stored name -> sha of what this server fetched or put
        self.target = {}            # local name -> stored name, when a conflict moved it
        self.dirty = set()
        self.lock, self.put_lock = threading.Lock(), threading.Lock()
        self.puts, self.last_sync, self.last_error = 0, None, None
        os.makedirs(folder, exist_ok=True)

    # ---------------- GitHub ----------------
    def req(self, method, path, body=None):
        r = urllib.request.Request(API + path, method=method,
                                   data=None if body is None else json.dumps(body).encode("utf-8"),
                                   headers={"Authorization": f"Bearer {self.token}",
                                            "Accept": "application/vnd.github+json",
                                            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cert3nf-study"})
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read() or b"null")

    def path(self, name):
        return f"/repos/{self.repo}/contents/{urllib.parse.quote(PREFIX + '/' + name)}"

    def fetch_all(self, tries=30):
        """fetch, tried again while GitHub cannot be reached: starting without the stored sessions would begin a
        participant's session anew"""
        for k in range(tries):
            try:
                return self.fetch()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):                        # a wrong token: puts fail too, nothing is overwritten
                    self.last_error = f"{now()} fetch: {e!r}"
                    return 0
                err = e
            except OSError as e:
                err = e
            log("fetch failed, trying again:", repr(err))
            time.sleep(min(2 * (k + 1), 20))
        raise SystemExit("store: the session files cannot be fetched")

    def fetch(self, sub=""):
        """copy the repository's session files to the local folder; returns how many were copied"""
        if not self.durable:
            return 0
        try:
            items = self.req("GET", (self.path(sub.rstrip("/")) if sub else
                                     f"/repos/{self.repo}/contents/{PREFIX}") + f"?ref={self.branch}")
        except urllib.error.HTTPError as e:
            if e.code == 404:                                   # no session yet
                return 0
            raise
        n = 0
        for it in items:
            name = sub + it["name"]
            if it["type"] == "dir":
                n += self.fetch(name + "/")
                continue
            if not name.endswith(".jsonl"):
                continue
            self.sha[name] = it["sha"]
            data = base64.b64decode(self.req("GET", f"/repos/{self.repo}/git/blobs/{it['sha']}")["content"])
            local = os.path.join(self.folder, *name.split("/"))
            if not os.path.exists(local) or os.path.getsize(local) < len(data):
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local, "wb") as fh:
                    fh.write(data)
                n += 1
        return n

    def put(self, name):
        with open(os.path.join(self.folder, *name.split("/")), "rb") as fh:
            data = fh.read()
        data = data[:data.rfind(b"\n") + 1]                     # complete lines only
        lines = data.count(b"\n")
        target = self.target.get(name, name)
        body = {"message": f"{target}: {lines} lines", "branch": self.branch,
                "content": base64.b64encode(data).decode("ascii")}
        if target in self.sha:
            body["sha"] = self.sha[target]
        try:
            r = self.req("PUT", self.path(target), body)
        except urllib.error.HTTPError as e:
            if e.code not in (409, 422):
                raise
            if target not in self.sha:                          # a stored file this server never saw: kept
                alt = target[:-len(".jsonl")] + time.strftime(".conflict-%Y%m%d-%H%M%S.jsonl")
                self.last_error = f"{now()} {target} was already in the repository; this one is stored as {alt}"
                log(self.last_error)
                self.target[name] = target = alt
                r = self.req("PUT", self.path(alt), {**body, "message": f"{alt}: {lines} lines"})
            else:                                               # a stale sha of a file this server wrote
                body["sha"] = self.req("GET", self.path(target) + f"?ref={self.branch}")["sha"]
                r = self.req("PUT", self.path(target), body)
        self.sha[target] = r["content"]["sha"]
        self.puts += 1

    def delete(self, path):
        """a test session that the experimenter reset: removed here and in the repository"""
        name = os.path.relpath(path, self.folder).replace(os.sep, "/")
        if os.path.exists(path):
            os.remove(path)
        if self.durable:
            with self.put_lock:
                with self.lock:
                    self.dirty.discard(name)
                target = self.target.pop(name, name)
                try:
                    sha = self.sha.pop(target, None) or self.req("GET", self.path(target) + f"?ref={self.branch}")["sha"]
                    self.req("DELETE", self.path(target), {"message": f"{target}: reset", "sha": sha,
                                                           "branch": self.branch})
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise

    # ---------------- the sessions' side ----------------
    def changed(self, path):
        """called by a session after every line it writes"""
        if self.durable:
            with self.lock:
                self.dirty.add(os.path.relpath(path, self.folder).replace(os.sep, "/"))

    def flush(self):
        with self.put_lock:
            with self.lock:
                names, self.dirty = self.dirty, set()
            for name in sorted(names):
                try:
                    self.put(name)
                    self.last_sync = now()
                except Exception as e:                          # noqa: BLE001 (kept dirty, tried again)
                    self.last_error = f"{now()} {name}: {e!r}"
                    log(self.last_error)
                    with self.lock:
                        self.dirty.add(name)

    def start(self):
        if self.durable:
            def loop():
                while True:
                    time.sleep(SYNC)
                    self.flush()
            threading.Thread(target=loop, daemon=True).start()

    def state(self):
        with self.lock:
            pending = len(self.dirty)
        return {"durable": self.durable, "repo": self.repo, "puts": self.puts, "last_sync": self.last_sync,
                "last_error": self.last_error, "pending": pending}
