"""Self-check for run.py: python3 tests/test_run.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run  # noqa: E402

with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, ".env")
    with open(path, "wb") as handle:  # Notepad style: BOM + CRLF + quotes
        handle.write(b'\xef\xbb\xbfHEXUDON_TOKEN="x.y.z"\r\n# note\r\nGAME_ID = abc \r\n')
    assert run.read_env(path) == {"HEXUDON_TOKEN": "x.y.z", "GAME_ID": "abc"}

secret = {"HEXUDON_TOKEN": "secret-token"}
bridge, solver = run.commands(dict(secret, MATCH_ID="m-1"), "", 1, "local", 7)
assert bridge is None and solver[solver.index("--match") + 1] == "m-1"
assert "secret-token" not in " ".join(solver)

config = dict(secret, GAME_ID="https://example/competition/game/abc:89?x=1")
live_bridge, live = run.commands(config, "", 1, "local", 7)
dry_bridge, dry = run.commands(config, "--dry-run", 1, "local", 7)
check_bridge, check_solver = run.commands(config, "--check", 1, "local", 7)
replay = live[live.index("--replay") + 1]
assert os.path.basename(replay) == "abc-89.jsonl"
assert dry[dry.index("--replay") + 1] != replay
assert live_bridge[live_bridge.index("--replay") + 1] == replay  # bridge and solver share it
assert "--dry-run" in dry_bridge and "--dry-run" not in live_bridge
assert check_solver is None and "--check" in check_bridge
assert "secret-token" not in " ".join(live_bridge + live + dry_bridge + dry + check_bridge)

for bad, flag in (({}, ""), ({"MATCH_ID": "m-1", "GAME_ID": "a"}, ""), ({"MATCH_ID": "m-1"}, "--check")):
    try:
        run.commands(bad, flag, 1, "local", 7)
    except SystemExit:
        continue
    raise AssertionError("accepted %r %s" % (bad, flag))

print("ok")
