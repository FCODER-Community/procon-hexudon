"""Offline check of tools/hexudon_bridge.py against a fake server: python3 tests/test_bridge.py"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import fake_hexudon as fake  # noqa: E402
import hexudon_bridge as bridge_module  # noqa: E402

games = fake.default_games()
games["q-fixed:" + fake.TEAM] = fake.Game(True, status="in_progress")
server = fake.serve(games)
upstream = bridge_module.Upstream("http://127.0.0.1:%d" % server.server_port, fake.TOKEN)
wait_all = json.dumps([[-fake.STEPS]] * len(fake.START)).encode()

assert bridge_module.split_game_id("https://x/competition/game/abc?tab=1") == ("abc", "")
assert bridge_module.split_game_id("abc%3A7") == ("abc", "7")
assert bridge_module.resolve_match(upstream, "q-active") == ("active", "q-active")
assert bridge_module.resolve_match(upstream, "q-practice") == ("practice", "q-practice:7")
assert bridge_module.resolve_match(upstream, "q-practice:7") == ("practice", "q-practice:7")

for mode, game_id in (("active", "q-active"), ("practice", "q-practice:7")):
    game = games[game_id]
    bridge = bridge_module.Bridge(upstream, mode, game_id, submit=True)
    status, setup = bridge.setup()
    assert status == 200 and setup["agents"] == fake.START
    assert (setup["startsAt"] == 0) == bridge.practice
    assert bridge.state()[0] == 425 and bridge.result()[0] == 404
    assert bridge.assignment(b"[0,1,0]") == (200, {"valid": True})
    assert game.role_posts == [[0, 1, 0]]
    for day in range(fake.DAYS):
        bridge.state_cache = (0.0, None)
        status, state = bridge.state()
        assert status == 200 and state["day"] == day and state["endsAt"] > 1e11, state
        assert "fuel" not in state["agents"][1]  # refuel truck
        assert bridge.actions(wait_all) == (200, {"day": day + 1, "valid": True})
        assert bridge.actions(wait_all)[1]["valid"]  # resend: cached ACK, no second POST
    assert len(game.plans) == fake.DAYS
    bridge.state_cache = (0.0, None)
    assert bridge.state()[0] == 404 and bridge.result()[0] == 200

# A rejected plan is reported to the solver, not cached.
game = games["q-fixed:7"]
bridge = bridge_module.Bridge(upstream, "practice", "q-fixed:7", submit=True)
bridge.state()
assert bridge.actions(b"[[-1],[-1],[-1]]")[1]["valid"] is False and not bridge.submitted

with tempfile.TemporaryDirectory() as directory:
    # Roles already fixed on the server: they are imported and a stale replay is moved away.
    replay = os.path.join(directory, "r.jsonl")
    with open(replay, "w") as handle:
        handle.write('{"kind":"old"}\n')
    bridge.prepare(replay)
    with open(replay) as handle:
        text = handle.read()
    assert '"assignment"' in text and "old" not in text
    assert len(os.listdir(directory)) == 2  # new replay plus the .bak

    # Dry-run writes a plan and never POSTs.
    dry = bridge_module.Bridge(upstream, "practice", "q-fixed:7", submit=False, plan_dir=directory)
    dry.state()
    assert dry.actions(wait_all)[1]["dryRun"] and not game.plans and not game.role_posts
    assert os.path.exists(os.path.join(directory, "plan-day0.json"))

server.shutdown()
print("ok")
