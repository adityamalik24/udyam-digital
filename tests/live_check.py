"""Paced run with Gemini on. Uses free-tier quota, so it's manual: python tests/live_check.py [seconds between turns]
Reports real successful LLM calls, because a run where every call failed proves nothing."""
import os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
os.environ["LIVE_LLM"] = "1"
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "live.db")
import yaml
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import run_scenarios as rs
from core import llm

PACE = float(sys.argv[1]) if len(sys.argv) > 1 else 13
ONLY = set(sys.argv[2:])  # optional scenario ids
calls = {"ok": 0, "failed": 0}
raw_call, raw_turn, slow = llm._call, rs.turn, []


def counted(system, user, c=None):
    if time.time() < llm._paused_until:
        calls["failed"] += 1
        return None
    out = raw_call(system, user, c)
    calls["ok" if out else "failed"] += 1
    return out


def paced(s, text):
    start = time.time()
    reply = raw_turn(s, text)
    took = time.time() - start
    slow.append(took)
    print(f"    [{took:4.1f}s] {text[:60]!r} -> {reply[:170]!r}".replace("\\n", " "), flush=True)
    time.sleep(PACE)
    return reply


llm._call, rs.turn = counted, paced
assert llm.client() is not None, "no LLM_API_KEY set"
fails = 0
scs = yaml.safe_load(pathlib.Path(__file__).with_name("advisor_live.yaml").read_text(encoding="utf-8"))
scs = [sc for sc in scs if not ONLY or sc["id"] in ONLY]
for sc in scs:
    errs, _ = rs.run(sc)
    fails += bool(errs)
    print("PASS" if not errs else f"FAIL {errs}", sc["id"], sc["name"], flush=True)
slow.sort()
print(f"\n{len(scs) - fails}/{len(scs)} passed; LLM calls ok {calls['ok']}, failed or skipped {calls['failed']}; turn time median {slow[len(slow) // 2]:.1f}s, slowest {slow[-1]:.1f}s")
