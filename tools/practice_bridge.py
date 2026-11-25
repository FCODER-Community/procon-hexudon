#!/usr/bin/env python3
"""Local bridge: BTC contract (/api/v1/matches/{id}/...) -> HEXUDON practice API (/api/game/...).

Lets `udonshield_btc http --url http://127.0.0.1:PORT` play a self-paced practice
game without changing the solver. The real token is read ONLY from the
HEXUDON_TOKEN environment variable of this process and is sent only to the
upstream HTTPS host. The solver process authenticates to this bridge with a
throwaway local secret ("local" by default).

Safety defaults:
  * dry-run: the first plan is written to disk and NOTHING is submitted upstream.
    Pass --submit to really POST /api/game/practice/actions.
  * a day is submitted at most once; resends (lost ACK) get the cached ACK, so a
    self-paced server that already advanced to the next day never receives the
    plan of the previous day.
  * agent roles are never changed; they are read from the server (/day kinds).
    --seed-replay writes them into the solver replay so the solver uses them.

Stdlib only (Python 3.8+).
"""
import argparse
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


def log(*parts):
    print("[bridge]", *parts, file=sys.stderr, flush=True)


class Upstream:
    def __init__(self, base, game_id, token, timeout):
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS):
            raise SystemExit("refusing to send the token over a non-HTTPS upstream: " + base)
        self.base = base.rstrip("/")
        self.game_id = game_id
        self.token = token
        self.timeout = timeout

    def _call(self, method, path, query=None, body=None):
        url = self.base + path
        if query is not None:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
            # Cloudflare-fronted servers reject the default "Python-urllib" agent with HTTP 403.
            "User-Agent": "UDON-SHIELD/1.0 (practice-bridge)",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            status = error.code
        # URLError / timeouts propagate: the caller maps them to HTTP 503 (transient).
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw

    def get(self, path):
        return self._call("GET", path, query={"game_id": self.game_id})

    def post(self, path, body):
        return self._call("POST", path, body=body)


class Bridge:
    def __init__(self, upstream, args):
        self.up = upstream
        self.args = args
        self.lock = threading.Lock()
        self.submit_lock = threading.Lock()  # one submission at a time; resends wait and reuse the ACK
        self.board = None
        self.served_day = None
        self.ends = {}
        self.submitted = {}
        self.dry_plan = None
        self.last_score_check = 0.0
        self.last_score = None
        self.team = upstream.game_id.split(":")[-1]

    # ---- upstream helpers -------------------------------------------------
    def get_board(self):
        if self.board is None:
            status, board = self.up.get("/api/game/board")
            if status != 200 or not isinstance(board, dict):
                raise RuntimeError("upstream /board returned %s: %s" % (status, str(board)[:200]))
            self.board = board
        return self.board

    def initial_positions(self):
        cache = self.args.cache
        status, day = self.up.get("/api/game/day")
        if status == 200 and isinstance(day, dict) and int(day.get("day", -1)) == 0:
            positions = [int(a["pos"]) for a in day["agents"]]
            self.save_cache(positions)
            return positions
        if self.args.initial_agents:
            return [int(x) for x in self.args.initial_agents.split(",")]
        if cache and os.path.exists(cache):
            with open(cache, encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("game_id") == self.up.game_id:
                return [int(x) for x in data["agents"]]
        raise RuntimeError(
            "initial agent positions unknown (game is past day 0): pass --initial-agents p1,p2,...")

    def save_cache(self, positions):
        if not self.args.cache:
            return
        with open(self.args.cache, "w", encoding="utf-8") as handle:
            json.dump({"game_id": self.up.game_id, "agents": positions}, handle)

    # ---- BTC-contract endpoints ------------------------------------------
    def setup(self):
        board = self.get_board()
        setup = {
            "agents": self.initial_positions(),
            "busyThreshold": int(board["busyThreshold"]),
            "daySeconds": [max(1, int(round(float(x)))) for x in board["daySeconds"]],
            "daySteps": [int(x) for x in board["daySteps"]],
            "fuelLimits": int(board["fuelLimits"]),
            "jammedThreshold": int(board["jammedThreshold"]),
            "map": board["map"],
            "players": int(board["players"]),
            "spots": board["spots"],
            "startsAt": int(float(board["startsAt"])),
        }
        return 200, setup

    def state(self):
        board = self.get_board()
        total = len(board["daySteps"])
        with self.lock:
            if self.dry_plan is not None:
                return 404, {"error": "dry-run finished"}
            if self.served_day is not None and (self.served_day + 1) >= total \
                    and self.served_day in self.submitted:
                return 404, {"error": "all days submitted"}
        status, day = self.up.get("/api/game/day")
        if status != 200 or not isinstance(day, dict):
            return (404 if status == 404 else 503), {"error": "upstream /day returned %s" % status}
        number = int(day["day"])
        if number >= total:
            return 404, {"error": "game finished"}
        full_fuel = int(board["fuelLimits"])
        agents = []
        for agent in day["agents"]:
            item = {"kind": int(agent["kind"]), "pos": int(agent["pos"])}
            if item["kind"] == 0:
                item["fuel"] = int(agent.get("fuel", full_fuel))
            agents.append(item)  # tanker fuel is unused; the solver defaults it
        with self.lock:
            self.served_day = number
            seconds = float(board["daySeconds"][number])
            self.ends.setdefault(number, int(time.time() * 1000 + seconds * 1000))
            ends_at = self.ends[number]
        state = {
            "day": number,
            "endsAt": ends_at,
            "agents": agents,
            "others": day.get("others", []),
            "traffics": [{"pos": int(t["pos"]), "status": int(t["status"])} for t in day.get("traffics", [])],
        }
        return 200, state

    def actions(self, raw_body):
        with self.submit_lock:
            return self._actions_locked(raw_body)

    def _actions_locked(self, raw_body):
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except ValueError:
            return 400, {"valid": False, "reason": "body is not JSON"}
        plan = body.get("actions") if isinstance(body, dict) else body
        if not isinstance(plan, list):
            return 400, {"valid": False, "reason": "plan is not an array"}
        with self.lock:
            day = self.served_day
            if day is None:
                return 409, {"valid": False, "reason": "no state served yet"}
            cached = self.submitted.get(day)
            if cached is not None:
                log("day", day, "already submitted; returning cached ACK")
                return 200, cached
        total = len(self.get_board()["daySteps"])
        if not self.args.submit:
            os.makedirs(self.args.plan_dir, exist_ok=True)
            path = os.path.join(self.args.plan_dir, "plan-day%d.json" % day)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"game_id": self.up.game_id, "day": day, "actions": plan}, handle)
            log("DRY-RUN: plan for day", day, "written to", path, "(not submitted; pass --submit)")
            ack = {"day": day + 1, "valid": True, "dryRun": True}
            with self.lock:
                self.submitted[day] = ack
                self.dry_plan = plan
            return 200, ack
        status, day_now = self.up.get("/api/game/day")
        if status != 200 or int(day_now.get("day", -1)) != day:
            return 409, {"valid": False, "reason": "upstream day moved or unreadable"}
        status, response = self.up.post(
            "/api/game/practice/actions",
            {"game_id": self.up.game_id, "day": day, "actions": plan})
        if 200 <= status < 300:
            ack = {"day": day + 1, "valid": True, "upstream": response}
            with self.lock:
                self.submitted[day] = ack
            log("day", day, "submitted OK (%d/%d)" % (day + 1, total))
            return 200, ack
        if status == 429 or status >= 500:
            return status, {"valid": False, "reason": "upstream %s" % status}
        log("day", day, "REJECTED upstream", status, str(response)[:300])
        return 200, {"day": day + 1, "valid": False, "reason": str(response)[:300]}

    def result(self):
        board = self.get_board()
        total = len(board["daySteps"])
        with self.lock:
            if self.dry_plan is not None:
                return 200, {"score": [0, 0, 0], "standings": [], "dryRun": True}
        now = time.time()
        if now - self.last_score_check < 1.0 and self.last_score is not None:
            status, score = self.last_score
        else:
            status, score = self.up.get("/api/game/practice/score")
            self.last_score_check, self.last_score = now, (status, score)
        if status != 200 or not isinstance(score, dict):
            return 404, {"error": "score unavailable"}
        detail = score.get("detail", {})
        mine = detail.get(self.team) or (next(iter(detail.values())) if detail else {})
        if int(mine.get("days_submitted", 0)) < total:
            return 404, {"error": "game not finished"}
        return 200, {
            "score": [mine.get("distinct_types"), mine.get("cumulative_daily_types"), mine.get("total_servings")],
            "standings": score.get("ranking", []),
            "detail": detail,
        }

    def select_roles(self, types):
        """POST /api/game/agent-types once (irreversible on the server), then verify via /day."""
        status, day = self.up.get("/api/game/day")
        if status != 200 or not isinstance(day, dict):
            raise RuntimeError("cannot read /day before selecting roles (HTTP %s): %s" % (status, str(day)[:200]))
        current = [int(a["kind"]) for a in day["agents"]]
        if int(day.get("day", -1)) != 0:
            raise RuntimeError("roles are fixed once play has started (server is at day %s)" % day.get("day"))
        if len(types) != len(current):
            raise RuntimeError("--select-roles has %d entries but the game has %d agents" % (len(types), len(current)))
        if current == types:
            log("roles already", types, "- not posting agent-types")
            return
        log("selecting roles (0=patrol, 1=tanker):", types, "- server currently shows", current)
        status, response = self.up.post("/api/game/agent-types", {"game_id": self.up.game_id, "types": types})
        if not (200 <= status < 300):
            raise RuntimeError("agent-types rejected (HTTP %s): %s" % (status, str(response)[:300]))
        status, day = self.up.get("/api/game/day")
        after = [int(a["kind"]) for a in day["agents"]] if status == 200 else None
        if after != types:
            raise RuntimeError("server roles after selection are %s, expected %s" % (after, types))
        log("roles confirmed by server:", after)

    def seed_replay(self, path):
        """Write the server's agent kinds into the solver replay as an accepted assignment."""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                if '"kind":"assignment"' in handle.read().replace(" ", ""):
                    log("replay already has an assignment; leaving it")
                    return
        status, day = self.up.get("/api/game/day")
        if status != 200:
            raise RuntimeError("cannot read /day to seed roles (HTTP %s): %s" % (status, str(day)[:200]))
        kinds = [int(a["kind"]) for a in day["agents"]]
        stamp = int(time.time() * 1000)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"atUnixMs": stamp, "kind": "assignment", "body": kinds}) + "\n")
            handle.write(json.dumps({"atUnixMs": stamp, "kind": "assignment_result", "status": 200,
                                     "body": {"valid": True}}) + "\n")
        log("seeded roles from server kinds:", kinds, "(0=patrol, 1=tanker) ->", path)


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
            try:
                if method == "GET" and tail == "setup":
                    return self._send(*bridge.setup())
                if method == "GET" and tail == "start":
                    return self._send(200, {"started": True})
                if method == "GET" and tail == "state":
                    return self._send(*bridge.state())
                if method == "GET" and tail == "result":
                    return self._send(*bridge.result())
                if method == "POST" and tail == "assignment":
                    return self._send(200, {"valid": True})  # roles are fixed by the server; see --seed-replay
                if method == "POST" and tail == "actions":
                    return self._send(*bridge.actions(body))
                return self._send(404, {"error": "unknown route"})
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                log("upstream transport error:", error)
                return self._send(503, {"error": "upstream unreachable"})
            except Exception as error:  # noqa: BLE001 - report, never crash the loop
                log("bridge error:", repr(error))
                return self._send(500, {"error": str(error)})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", default="https://hexudon.hairbui76.id.vn")
    parser.add_argument("--game-id", required=True, help="e.g. d7471f1d-...:89 (with the :team suffix)")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--local-token", default="local")
    parser.add_argument("--submit", action="store_true", help="really POST plans (default: dry-run, first day only)")
    parser.add_argument("--initial-agents", default="", help="day-0 positions p1,p2,... if the game is past day 0")
    parser.add_argument("--cache", default="practice-bridge-cache.json")
    parser.add_argument("--plan-dir", default="artifacts/practice-plans")
    parser.add_argument("--select-roles", default="", help="e.g. 1,1,1,0,0 (0=patrol,1=tanker): POST agent-types ONCE, irreversible; needs --submit")
    parser.add_argument("--seed-replay", default="", help="solver replay file to seed with the server's roles")
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    token = os.environ.get("HEXUDON_TOKEN", "").strip()
    if not token:
        raise SystemExit("HEXUDON_TOKEN is not set (it is read only from the environment)")
    upstream = Upstream(args.upstream, args.game_id, token, args.timeout)
    bridge = Bridge(upstream, args)
    if args.select_roles:
        if not args.submit:
            raise SystemExit("--select-roles writes to the server (irreversible); add --submit to confirm")
        bridge.select_roles([int(x) for x in args.select_roles.split(",")])
    if args.seed_replay:
        bridge.seed_replay(args.seed_replay)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bridge, args.local_token))
    log("listening on 127.0.0.1:%d | upstream %s | mode %s" % (
        args.port, args.upstream, "SUBMIT" if args.submit else "DRY-RUN"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
