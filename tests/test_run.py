"""Self-check for run.py: python3 tests/test_run.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run  # noqa: E402

with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, ".env")
    with open(path, "wb") as handle:  # Notepad style: BOM + CRLF + quotes
        handle.write(b'\xef\xbb\xbfHEXUDON_TOKEN="bot-x"\r\n# note\r\nMATCH_ID = m-1 \r\n')
    assert run.read_env(path) == {"HEXUDON_TOKEN": "bot-x", "MATCH_ID": "m-1"}

secret = {"HEXUDON_TOKEN": "bot-secret"}
bridge, solver = run.commands(dict(secret, MATCH_ID="m-1"), False, 1, "local", 7)
assert bridge is None and solver[solver.index("--match") + 1] == "m-1"
assert "bot-secret" not in " ".join(solver)

dry_bridge, dry = run.commands(dict(secret, GAME_ID="abc:89"), False, 1, "local", 7)
live_bridge, live = run.commands(dict(secret, GAME_ID="abc:89"), True, 1, "local", 7)
dry_replay = dry[dry.index("--replay") + 1]
live_replay = live[live.index("--replay") + 1]
assert dry_replay != live_replay and ":" not in live_replay
assert "--submit" not in dry_bridge and "--submit" in live_bridge
assert "bot-secret" not in " ".join(dry_bridge + dry + live_bridge + live)

for bad in ({}, {"MATCH_ID": "m-1", "GAME_ID": "a:1"}):
    try:
        run.commands(bad, False, 1, "local", 7)
    except SystemExit:
        continue
    raise AssertionError("accepted %r" % bad)

print("ok")
