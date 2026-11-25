#!/usr/bin/env python3
"""Chạy bot UDON-SHIELD theo cấu hình trong .env (Windows và Ubuntu).

    python3 run.py --check     # chỉ kiểm tra token và mã trận, không gửi gì
    python3 run.py             # chơi thật: chọn vai trò và nộp plan
    python3 run.py --dry-run   # tính plan một ngày, ghi ra đĩa, không nộp

Trên Windows gõ "python" thay cho "python3".
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
FLAGS = ([], ["--check"], ["--dry-run"], ["--submit"])  # --submit is the default, kept as an alias


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


def solver_binary():
    name = "udonshield_btc" + (".exe" if os.name == "nt" else "")
    paths = [os.path.join(ROOT, "build-release", name),
             os.path.join(ROOT, "build-release", "Release", name)]  # Visual Studio generator
    return next((path for path in paths if os.path.exists(path)), paths[0])


def commands(config, flag, port, local_token, stamp):
    """Return (bridge command or None, solver command or None)."""
    match_id = config.get("MATCH_ID", "")
    game_id = config.get("GAME_ID", "")
    if bool(match_id) == bool(game_id):
        raise SystemExit("Điền đúng một trong GAME_ID hoặc MATCH_ID trong .env")
    if match_id and flag in ("--check", "--dry-run"):
        raise SystemExit("%s chỉ dùng được với GAME_ID" % flag)

    # GAME_ID may be a pasted URL; ':' is illegal in Windows file names.
    short = (match_id or game_id).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "-", short)
    # A dry-run ACK must never be resumed by a real run, so each dry-run gets its own replay.
    if flag == "--dry-run":
        name += "-dryrun-%d" % stamp
    replay = os.path.join("artifacts", "btc", name + ".jsonl")
    solver = [
        solver_binary(), "http",
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
        sys.executable, os.path.join(ROOT, "tools", "hexudon_bridge.py"),
        "--game-id", game_id,
        "--mode", config.get("MODE") or "auto",
        "--port", str(port),
        "--local-token", local_token,
    ]
    if url:
        bridge += ["--upstream", url]
    if flag == "--check":
        return bridge + ["--check"], None
    bridge += ["--replay", replay]
    if flag == "--dry-run":
        bridge.append("--dry-run")
    solver += ["--match", "game", "--url", "http://127.0.0.1:%d" % port]
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
    raise SystemExit("Bridge không khởi động được, xem thông báo ở trên")


def main(argv):
    if argv not in FLAGS:
        raise SystemExit(__doc__)
    flag = argv[0] if argv else ""
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        raise SystemExit("Chưa có .env. Copy .env.example thành .env rồi điền.")
    config = read_env(env_path)
    token = config.get("HEXUDON_TOKEN") or os.environ.get("HEXUDON_TOKEN", "")
    if not token:
        raise SystemExit("Chưa điền HEXUDON_TOKEN trong .env")

    port, local_token = free_port(), secrets.token_hex(16)
    bridge_command, solver_command = commands(config, flag, port, local_token, int(time.time()))
    if solver_command and not os.path.exists(solver_command[0]):
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
            bridge_env = dict(os.environ, HEXUDON_TOKEN=token)
            if not solver_command:
                return subprocess.call(bridge_command, cwd=ROOT, env=bridge_env)
            bridge = subprocess.Popen(bridge_command, cwd=ROOT, env=bridge_env)
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
    # Windows consoles may not be UTF-8; never die on a Vietnamese message.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main(sys.argv[1:]))
