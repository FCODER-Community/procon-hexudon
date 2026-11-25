#!/usr/bin/env python3
"""Local bridge: solver contract (/api/v1/matches/{id}/...) -> HEXUDON game API (/api/game/...).

Normally started by run.py. It handles both kinds of match:
  active    timed match, bare game id, POST /api/game/actions
  practice  self-paced match, "game_id:team_id", POST /api/game/practice/actions

The real token is read only from HEXUDON_TOKEN and sent only to an HTTPS
upstream (or localhost). The solver authenticates with a throwaway local secret.
Stdlib only (Python 3.8+).
"""
import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
DEFAULT_UPSTREAM = "https://hexudon.hairbui76.id.vn"
STATE_CACHE_SECONDS = 0.4  # the organisers ask for at most ~5 requests per second
PRACTICE_MIN_DAY_SECONDS = 10  # self-paced: no real deadline, give the solver room


def log(*parts):
    print("[bridge]", *parts, file=sys.stderr, flush=True)


def token_claims(token):
    """Unverified JWT payload; {} if the token is not a JWT."""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}


def split_game_id(value):
    """Accept a bare id, "id:team" or a pasted web URL; return (question_id, team or "")."""
    value = value.strip().split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    value = urllib.parse.unquote(value)
    question, _, team = value.partition(":")
    return question, team


class Upstream:
    def __init__(self, base, token, timeout=8.0):
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS):
            raise SystemExit("refusing to send the token over a non-HTTPS upstream: " + base)
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, method, path, query=None, body=None):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
            # Cloudflare rejects the default "Python-urllib" agent with HTTP 403.
            "User-Agent": "UDON-SHIELD/1.0 (hexudon-bridge)",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status, raw = response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read().decode("utf-8", "replace")
        # URLError / timeouts propagate: the HTTP handler maps them to 503 (retried).
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw


def explain(status, payload):
    hint = {401: " (token sai hoặc hết hạn)", 403: " (token không có quyền với trận này)",
            404: " (sai mã trận, hoặc đội không thuộc trận này)"}.get(status, "")
    return "HTTP %s%s: %s" % (status, hint, str(payload)[:300])


def resolve_match(upstream, game_id, mode="auto"):
    """Return (mode, game id to send), e.g. ("practice", "uuid:7")."""
    question, team = split_game_id(game_id)
    if not question:
        raise SystemExit("GAME_ID trống")
    if mode == "auto" and team:
        mode = "practice"
    team = team or str(token_claims(upstream.token).get("id", ""))
    composite = "%s:%s" % (question, team)
    if mode == "auto":
        status, payload = upstream.call("GET", "/manager/api/question/" + urllib.parse.quote(question))
        data = payload.get("question_data") if status == 200 and isinstance(payload, dict) else None
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            if data.get("is_practice") and data.get("no_reset"):
                raise SystemExit("Đây là trận 'Luyện tập thi đấu' (competitive practice). Bot chưa hỗ trợ loại này.")
            mode = "practice" if data.get("is_practice") else "active"
    if mode == "auto":  # the manager API did not answer: ask the game service which game exists
        for candidate, full in (("practice", composite), ("active", question)):
            status, payload = upstream.call("GET", "/api/game/state", {"game_id": full})
            if status == 200:
                return candidate, full
        raise SystemExit("Không tìm thấy trận. " + explain(status, payload))
    if mode == "practice":
        if not team:
            raise SystemExit("Không đọc được team id từ token. Điền GAME_ID dạng game_id:team_id")
        return mode, composite
    return mode, question


class Bridge:
    def __init__(self, upstream, mode, game_id, submit, plan_dir="artifacts/practice-plans"):
        self.up = upstream
        self.practice = mode == "practice"
        self.game_id = game_id
        self.submit = submit
        self.plan_dir = plan_dir
        self.lock = threading.RLock()
        self.submit_lock = threading.Lock()  # resends wait and reuse the first ACK
        self.config = None
        self.state_cache = (0.0, None)
        self.day_cache = None
        self.served_day = None
        self.practice_ends = {}
        self.submitted = {}
        self.dry_run_done = False

    # ---- upstream helpers -------------------------------------------------
    def game_get(self, path):
        return self.up.call("GET", path, {"game_id": self.game_id})

    def match_state(self, fresh=False):
        with self.lock:
            at, cached = self.state_cache
            if not fresh and cached and time.time() - at < STATE_CACHE_SECONDS:
                return cached
            result = self.game_get("/api/game/state")
            self.state_cache = (time.time(), result)
            return result

    def get_config(self):
        if self.config is None:
            status, config = self.game_get("/api/game/config")
            if status != 200 or not isinstance(config, dict) or "map" not in config or "agents" not in config:
                return (425 if status in (200, 409, 425) else status), config
            self.config = config
        return 200, self.config

    def total_days(self):
        status, config = self.get_config()
        return len(config["daySteps"]) if status == 200 else 0

    def current_day(self, number):
        """GET /day, fetched once per day (it does not change within a day)."""
        with self.lock:
            if self.day_cache and self.day_cache["day"] == number:
                return 200, self.day_cache
        status, day = self.game_get("/api/game/day")
        if status == 200 and isinstance(day, dict) and day.get("day") == number:
            with self.lock:
                self.day_cache = day
        return status, day

    # ---- solver-contract endpoints ----------------------------------------
    def setup(self):
        status, config = self.get_config()
        if status != 200:
            return status, {"error": explain(status, config)}
        setup = dict(config)
        floor = PRACTICE_MIN_DAY_SECONDS if self.practice else 1
        setup["daySeconds"] = [max(floor, int(round(float(x)))) for x in config["daySeconds"]]
        # A practice match has no start countdown; startsAt=0 lets the solver run its full role search.
        setup["startsAt"] = 0 if self.practice else int(float(config.get("startsAt", 0)))
        return 200, setup

    def assignment(self, raw_body):
        types = json.loads(raw_body.decode("utf-8"))
        if not self.submit:
            return 200, {"valid": True, "dryRun": True}
        status, state = self.match_state(fresh=True)
        if status == 200 and (state.get("selection_opens_in") or 0) > 0:
            return 425, {"error": "role selection not open yet"}
        status, response = self.up.call("POST", "/api/game/agent-types",
                                        body={"game_id": self.game_id, "types": types})
        if status == 429 or status >= 500:
            return status, {"error": "upstream %s" % status}
        with self.lock:
            self.state_cache = (0.0, None)
        if not 200 <= status < 300:
            log("roles REJECTED:", explain(status, response))
            return 200, {"valid": False, "reason": str(response)[:300]}
        log("roles submitted (0=patrol, 1=refuel):", types)
        return 200, {"valid": True}

    def start(self):
        status, state = self.match_state()
        if status == 200 and state.get("status") in ("in_progress", "finished"):
            return 200, {"started": True}
        if status in (200, 409):
            return 425, {"error": "match not started"}
        return status, {"error": explain(status, state)}

    def state(self):
        if self.dry_run_done:
            return 404, {"error": "dry-run finished"}
        status, state = self.match_state()
        if status != 200:
            return status, {"error": explain(status, state)}
        if state.get("status") == "finished":
            return 404, {"error": "match finished"}
        if state.get("status") != "in_progress":
            return 425, {"error": "match not started"}
        status = self.get_config()[0]
        if status != 200:
            return status, {"error": "config unavailable"}
        number = int(state.get("day", 0))
        if number >= self.total_days():
            return 404, {"error": "match finished"}
        status, day = self.current_day(number)
        if status != 200 or not isinstance(day, dict):
            return (425 if status == 409 else status), {"error": explain(status, day)}
        number = int(day["day"])
        agents = []
        for agent in day["agents"]:
            item = {"kind": int(agent["kind"]), "pos": int(agent["pos"])}
            if item["kind"] == 0:
                item["fuel"] = int(agent["fuel"])
            agents.append(item)
        body = {"day": number, "agents": agents, "others": day.get("others", []),
                "traffics": [{"pos": int(t["pos"]), "status": int(t["status"])} for t in day.get("traffics", [])]}
        if self.practice:
            seconds = max(PRACTICE_MIN_DAY_SECONDS, float(self.config["daySeconds"][number]))
            body["endsAt"] = self.practice_ends.setdefault(number, int((time.time() + seconds) * 1000))
        elif day.get("endsAt"):
            value = float(day["endsAt"])  # the server's real deadline, seconds or milliseconds
            body["endsAt"] = int(value if value >= 1e11 else value * 1000)
        elif state.get("day_deadline_in") is not None:
            body["endsAt"] = int((time.time() + float(state["day_deadline_in"])) * 1000)
        with self.lock:
            self.served_day = number
        return 200, body

    def actions(self, raw_body):
        with self.submit_lock:
            plan = json.loads(raw_body.decode("utf-8"))
            if isinstance(plan, dict):
                plan = plan.get("actions")
            day = self.served_day
            if not isinstance(plan, list) or day is None:
                return 400, {"valid": False, "reason": "no state served yet or bad plan"}
            if day in self.submitted:
                log("day", day, "already submitted; returning cached ACK")
                return 200, self.submitted[day]
            if not self.submit:
                os.makedirs(self.plan_dir, exist_ok=True)
                path = os.path.join(self.plan_dir, "plan-day%d.json" % day)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump({"game_id": self.game_id, "day": day, "actions": plan}, handle)
                log("DRY-RUN: plan for day", day, "written to", path, "(not submitted)")
                self.dry_run_done = True
                return 200, {"day": day + 1, "valid": True, "dryRun": True}
            path = "/api/game/practice/actions" if self.practice else "/api/game/actions"
            status, response = self.up.call("POST", path,
                                            body={"game_id": self.game_id, "day": day, "actions": plan})
            if status == 429 or status >= 500:
                return status, {"valid": False, "reason": "upstream %s" % status}
            if not 200 <= status < 300 or (isinstance(response, dict) and response.get("valid") is False):
                log("day", day, "REJECTED:", explain(status, response))
                return 200, {"day": day + 1, "valid": False, "reason": str(response)[:300]}
            ack = {"day": day + 1, "valid": True}
            self.submitted[day] = ack
            with self.lock:
                self.state_cache = (0.0, None)  # a practice match advances right after a submit
            log("day %d/%d submitted OK" % (day + 1, self.total_days()))
            return 200, ack

    def result(self):
        if self.dry_run_done:
            return 200, {"dryRun": True}
        status, state = self.match_state()
        finished = status == 200 and state.get("status") == "finished"
        if not finished and not (self.practice and (self.total_days() - 1) in self.submitted):
            return 404, {"error": "match not finished"}
        status, score = self.game_get("/api/game/practice/score" if self.practice else "/api/game/result")
        if status != 200:
            return 404, {"error": explain(status, score)}
        return 200, {"result": score}

    # ---- startup ----------------------------------------------------------
    def prepare(self, replay):
        """Before the solver starts: drop a stale replay and import roles already fixed on the server."""
        status, state = self.match_state(fresh=True)
        if status != 200 or not isinstance(state, dict):
            raise SystemExit("Không đọc được trận %s. %s" % (self.game_id, explain(status, state)))
        phase = state.get("status")
        log("match", self.game_id, "| mode", "practice" if self.practice else "active",
            "| status", phase, "| day", state.get("day"), "|", "SUBMIT" if self.submit else "DRY-RUN")
        if phase == "finished":
            raise SystemExit("Trận đã kết thúc." + (" Muốn chơi lại: bấm reset trên web." if self.practice else ""))
        if phase == "selecting_agents" and not self.submit:
            raise SystemExit("Trận đang chờ chọn vai trò nên chưa dry-run được. Chạy không kèm --dry-run.")
        if not replay:
            return
        # Selection or day 0: nothing has been played, so an old replay belongs to an earlier (reset) game.
        if os.path.exists(replay) and (phase == "selecting_agents" or int(state.get("day") or 0) == 0):
            os.replace(replay, replay + ".bak-%d" % int(time.time()))
        if phase != "in_progress" or os.path.exists(replay):
            return
        status, day = self.game_get("/api/game/day")
        if status != 200 or not isinstance(day, dict):
            raise SystemExit("Không đọc được ngày hiện tại. " + explain(status, day))
        kinds = [int(a["kind"]) for a in day["agents"]]
        os.makedirs(os.path.dirname(os.path.abspath(replay)), exist_ok=True)
        stamp = int(time.time() * 1000)
        with open(replay, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"atUnixMs": stamp, "kind": "assignment", "body": kinds}) + "\n")
            handle.write(json.dumps({"atUnixMs": stamp, "kind": "assignment_result", "status": 200,
                                     "body": {"valid": True}}) + "\n")
        log("roles already fixed on the server:", kinds)

    def check(self):
        """Read-only diagnosis: no POST at all."""
        status, state = self.match_state(fresh=True)
        print("mode:", "practice" if self.practice else "active")
        print("game_id:", self.game_id)
        if status != 200:
            print("state:", explain(status, state))
            return 1
        for key in ("status", "day", "selection_opens_in", "selection_deadline_in", "day_deadline_in"):
            print("%s: %s" % (key, state.get(key)))
        status, config = self.get_config()
        if status != 200:
            print("config:", explain(status, config))
            return 0 if status == 425 else 1
        print("map: %sx%s | agents: %d | days: %d | daySteps: %s | daySeconds: %s" % (
            config["map"]["width"], config["map"]["height"], len(config["agents"]),
            len(config["daySteps"]), config["daySteps"], config["daySeconds"]))
        print("OK: token và mã trận dùng được.")
        return 0


def make_handler(bridge, local_token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def _send(self, status, payload):
            raw = json.dumps(payload).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                log("client closed the connection before the reply (it will resend; ACK is cached)")

        def _route(self, method):
            if self.headers.get("Authorization") != "Bearer " + local_token:
                return self._send(401, {"error": "bad local token"})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            tail = self.path.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            routes = {
                ("GET", "setup"): bridge.setup,
                ("GET", "start"): bridge.start,
                ("GET", "state"): bridge.state,
                ("GET", "result"): bridge.result,
                ("POST", "assignment"): lambda: bridge.assignment(body),
                ("POST", "actions"): lambda: bridge.actions(body),
            }
            if (method, tail) not in routes:
                return self._send(404, {"error": "unknown route"})
            try:
                status, payload = routes[(method, tail)]()
                if status in (401, 403):
                    log(payload.get("error", status))
                return self._send(status, payload)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                log("upstream transport error:", error)
                return self._send(503, {"error": "upstream unreachable"})
            except Exception as error:  # noqa: BLE001 - report, never crash the server
                log("bridge error:", repr(error))
                return self._send(500, {"error": str(error)})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-id", required=True, help="question id, id:team, or the game page URL")
    parser.add_argument("--mode", default="auto", choices=("auto", "active", "practice"))
    parser.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--local-token", default="local")
    parser.add_argument("--replay", default="", help="solver replay file (must match the solver's --replay)")
    parser.add_argument("--dry-run", action="store_true", help="plan one day, write it to disk, POST nothing")
    parser.add_argument("--check", action="store_true", help="read-only diagnosis, then exit")
    args = parser.parse_args()

    token = os.environ.get("HEXUDON_TOKEN", "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise SystemExit("HEXUDON_TOKEN is not set")
    expires = token_claims(token).get("exp")
    if expires and expires < time.time():
        raise SystemExit("Token đã hết hạn lúc %s. Lấy token mới (icon chìa khoá trên web)."
                         % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires)))
    upstream = Upstream(args.upstream, token)
    try:
        mode, game_id = resolve_match(upstream, args.game_id, args.mode)
        bridge = Bridge(upstream, mode, game_id, not args.dry_run)
        if args.check:
            sys.exit(bridge.check())
        bridge.prepare(args.replay)
    except urllib.error.URLError as error:
        raise SystemExit("Không kết nối được %s: %s" % (args.upstream, error.reason))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bridge, args.local_token))
    log("listening on 127.0.0.1:%d | upstream %s" % (args.port, args.upstream))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    # Windows consoles may not be UTF-8; never die on a Vietnamese message.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    main()
