#!/usr/bin/env python3
"""Chạy bot UDON-SHIELD theo cấu hình trong .env (Windows và Ubuntu).

    python3 run.py             # Ubuntu
    python run.py              # Windows
    python3 run.py --submit    # chế độ GAME_ID: gửi plan thật (mặc định dry-run)

Token chỉ được truyền qua biến môi trường, không nằm trên dòng lệnh.
"""
import os
import re
import secrets
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def read_env(path):
    values = {}
    # utf-8-sig: Notepad on Windows may add a BOM.
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return values


def commands(config, submit, port, local_token, stamp):
    """Return (bridge command or None, solver command)."""
    match_id = config.get("MATCH_ID", "")
    game_id = config.get("GAME_ID", "")
    if bool(match_id) == bool(game_id):
        raise SystemExit("Điền đúng một trong MATCH_ID hoặc GAME_ID trong .env")
    name = re.sub(r"[^A-Za-z0-9._-]", "-", match_id or game_id)  # ':' is illegal on Windows
    # A dry-run ACK must never be resumed by a real run, so each dry-run gets its own replay.
    if game_id and not submit:
        name += "-dryrun-%d" % stamp
    replay = os.path.join("artifacts", "btc", name + ".jsonl")
    solver = [
        os.path.join(ROOT, "build-release", "udonshield_btc" + (".exe" if os.name == "nt" else "")),
        "http",
        "--response-ms", config.get("RESPONSE_MS") or "5000",
        "--replay", replay,
    ]
    url = config.get("URL", "")
    if match_id:
        solver += ["--match", match_id]
        if url:
            solver += ["--url", url]
        return None, solver
    bridge = [
        sys.executable, os.path.join(ROOT, "tools", "practice_bridge.py"),
        "--game-id", game_id,
        "--port", str(port),
        "--local-token", local_token,
        "--seed-replay", replay,
    ]
    if url:
        bridge += ["--upstream", url]
    if config.get("INITIAL_AGENTS"):
        bridge += ["--initial-agents", config["INITIAL_AGENTS"]]
    if submit:
        bridge.append("--submit")
    solver += ["--match", "practice", "--url", "http://127.0.0.1:%d" % port]
    return bridge, solver


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_listening(process, port, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline and process.poll() is None:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit("Bridge không khởi động được, xem log [bridge] ở trên")


def main(argv):
    if argv not in ([], ["--submit"]):
        raise SystemExit(__doc__)
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        raise SystemExit("Chưa có .env. Copy .env.example thành .env rồi điền.")
    config = read_env(env_path)
    token = config.get("HEXUDON_TOKEN") or os.environ.get("HEXUDON_TOKEN", "")
    if not token:
        raise SystemExit("Chưa điền HEXUDON_TOKEN trong .env")

    port, local_token = free_port(), secrets.token_hex(16)
    bridge_command, solver_command = commands(config, bool(argv), port, local_token, int(time.time()))
    if not os.path.exists(solver_command[0]):
        raise SystemExit(
            "Chưa build bot. Chạy:\n"
            "  cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release\n"
            "  cmake --build build-release --parallel")
    os.makedirs(os.path.join(ROOT, "artifacts", "btc"), exist_ok=True)

    bridge = None
    try:
        solver_token = token
        if bridge_command:
            # The real token stays in the bridge; the solver only gets the local one.
            bridge = subprocess.Popen(bridge_command, cwd=ROOT, env=dict(os.environ, HEXUDON_TOKEN=token))
            wait_until_listening(bridge, port)
            solver_token = local_token
        return subprocess.call(solver_command, cwd=ROOT, env=dict(os.environ, HEXUDON_TOKEN=solver_token))
    except KeyboardInterrupt:
        return 130
    finally:
        if bridge:
            bridge.terminate()
            bridge.wait()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
