"""Minimal fake of the HEXUDON server, for offline tests of the bridge and run.py.

Shapes follow the public OpenAPI spec, the web client and the organisers' format document;
they are not a recording of the real server. All cells are plain (2 steps, 1 fuel per move).

    python3 tests/fake_hexudon.py PORT      # question ids: q-active, q-practice
"""
import base64
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEAM = "7"
TOKEN = "x.%s.y" % base64.urlsafe_b64encode(json.dumps({"id": int(TEAM)}).encode()).decode().rstrip("=")
SIZE, DAYS, STEPS, FUEL = 8, 4, 20, 40
START = [9, 13, 41]


def neighbour(pos, direction):  # even-r: even rows are shifted right
    row, col = divmod(pos, SIZE)
    shift = 1 if row % 2 == 0 else 0
    row, col = [(row - 1, col - 1 + shift), (row - 1, col + shift), (row, col + 1),
                (row + 1, col + shift), (row + 1, col - 1 + shift), (row, col - 1)][direction]
    if not (0 <= row < SIZE and 0 <= col < SIZE):
        raise ValueError("moved off the map")
    return row * SIZE + col


class Game:
    def __init__(self, practice, status="selecting_agents"):
        self.practice = practice
        self.status = status
        self.day = 0
        self.kinds = [0] * len(START)
        self.positions = list(START)
        self.fuel = [FUEL] * len(START)
        self.role_posts = []
        self.plans = []

    def config(self):
        return {"startsAt": time.time(), "daySeconds": [5] * DAYS, "daySteps": [STEPS] * DAYS,
                "map": {"width": SIZE, "height": SIZE, "cells": [[0] * SIZE for _ in range(SIZE)]},
                "spots": [{"brand": i % 3, "pos": p, "stocks": 2} for i, p in enumerate([2, 20, 29, 36, 50, 62])],
                "agents": START, "fuelLimits": FUEL, "players": 8, "busyThreshold": 2, "jammedThreshold": 4}

    def day_info(self):
        info = {"day": self.day, "others": [], "traffics": [],
                "agents": [{"kind": k, "pos": p, "fuel": f}
                           for k, p, f in zip(self.kinds, self.positions, self.fuel)]}
        if not self.practice:
            info["endsAt"] = int(time.time()) + 5
        return info

    def play(self, day, plan):
        if self.status != "in_progress" or day != self.day or len(plan) != len(START):
            raise ValueError("wrong day, status or agent count")
        for index, actions in enumerate(plan):
            used, position, moves = 0, self.positions[index], 0
            for action in actions:
                if action < 0:
                    used -= action
                else:
                    position, used, moves = neighbour(position, action), used + 2, moves + 1
            if used != STEPS:
                raise ValueError("agent %d uses %d of %d steps" % (index, used, STEPS))
            self.positions[index] = position
            if self.kinds[index] == 0:
                self.fuel[index] -= moves
        self.plans.append(plan)
        self.day += 1
        if self.day == DAYS:
            self.status = "finished"


def serve(games, port=0):
    """games maps the game id the bridge must send to a Game. Returns the running server."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def reply(self, status, body):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def handle_api(self, body):
            if self.headers.get("Authorization") != "Bearer " + TOKEN:
                return self.reply(401, {"detail": "bad token"})
            url = urllib.parse.urlparse(self.path)
            if url.path.startswith("/manager/api/question/"):
                practice = url.path.rsplit("/", 1)[-1] == "q-practice"
                return self.reply(200, {"question_data": json.dumps({"is_practice": practice, "no_reset": False})})
            game_id = (body or {}).get("game_id") or urllib.parse.parse_qs(url.query).get("game_id", [""])[0]
            game = games.get(game_id)
            if game is None:
                return self.reply(404, {"detail": "no such game " + game_id})
            name = url.path[len("/api/game/"):]
            if name == "state":
                return self.reply(200, {"status": game.status, "day": game.day, "selection_opens_in": 0})
            if name == "config":
                return self.reply(200, game.config())
            if name == "day":
                return self.reply(200, game.day_info())
            if name == "agent-types":
                game.kinds = body["types"]
                game.role_posts.append(body["types"])
                game.status = "in_progress"
                return self.reply(200, {"ok": True})
            if name == ("practice/actions" if game.practice else "actions"):
                try:
                    game.play(body["day"], body["actions"])
                except ValueError as error:
                    return self.reply(400, {"detail": str(error)})
                return self.reply(200, {"ok": True})
            if name == ("practice/score" if game.practice else "result"):
                return self.reply(200, {"days_played": len(game.plans)})
            return self.reply(404, {"detail": "wrong endpoint for this game: " + name})

        def do_GET(self):
            self.handle_api(None)

        def do_POST(self):
            self.handle_api(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def default_games():
    return {"q-active": Game(False), "q-practice:" + TEAM: Game(True)}


if __name__ == "__main__":
    server = serve(default_games(), int(sys.argv[1]))
    print("fake HEXUDON on http://127.0.0.1:%s token %s" % (sys.argv[1], TOKEN), flush=True)
    threading.Event().wait()
