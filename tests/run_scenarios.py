"""Advisor scenario suite. Run: python tests/run_scenarios.py. Exits non-zero on failure."""
import os, re, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
os.environ.setdefault("UDYAM_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
if not os.getenv("LIVE_LLM"): os.environ["LLM_API_KEY"] = ""  # offline unless asked
import yaml
from core.advisor import State, turn
from core.guardrails import check_reply
from core.rules import mentionable


def run(sc):
    s, reply, prev, errs = State(), "", None, []
    for t in sc["turns"]:
        prev = s.rec.quote.monthly if s.rec and s.rec.quote else prev
        reply = turn(s, t)
    items = s.rec.items if s.rec else {}
    if "items" in sc and set(items) != set(sc["items"]): errs.append(f"items {sorted(items)} != {sc['items']}")
    for p in sc.get("has", []):
        if p not in items: errs.append(f"missing {p} in {sorted(items)}")
    for p in sc.get("lacks", []):
        if p in items: errs.append(f"should lack {p}")
    for p, q in sc.get("qty", {}).items():
        if items.get(p) != q: errs.append(f"qty {p}={items.get(p)} want {q}")
    for key in ("reply_has", "reply_has2"):
        if key in sc and not re.search(sc[key], reply): errs.append(f"reply lacks /{sc[key]}/")
    if "reply_lacks" in sc and re.search(sc["reply_lacks"], reply): errs.append("reply leaked")
    if "history_lacks" in sc and any(sc["history_lacks"] in m for _, m in s.history): errs.append("history leaked")
    if sc.get("lang") and s.profile.language != sc["lang"]: errs.append(f"lang {s.profile.language}")
    if sc.get("handoff") and not s.handoff: errs.append("no handoff")
    if sc.get("no_rec") and items: errs.append("unexpected bundle")
    for k, v in sc.get("profile", {}).items():
        if getattr(s.profile, k) != v: errs.append(f"{k}={getattr(s.profile, k)} want {v}")
    for n in sc.get("need", []):
        if n not in s.profile.needs: errs.append(f"need {n} missing from {s.profile.needs}")
    for n in sc.get("no_need", []):
        if n in s.profile.needs: errs.append(f"wrong need {n}")
    if sc.get("reply_price_same") and not (s.rec and s.rec.quote and s.rec.quote.monthly == prev and f"{prev:,}" in reply): errs.append("price changed or missing")
    if "max_asked" in sc and len(s.asked) > sc["max_asked"]: errs.append(f"asked {s.asked}")
    if len(s.asked) > 6: errs.append(f"too many questions {s.asked}")
    if s.rec and s.rec.quote and len(sc["turns"]) and reply.count("₹") >= 2:
        bad = check_reply(reply, s.rec.quote, s.rec.alt_quote, mentionable(s.rec))
        if bad: errs.append(f"guardrail {bad}")
    return errs, reply


def main():
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).with_name("advisor_scenarios.yaml")
    fails = 0
    scs = yaml.safe_load(path.read_text(encoding="utf-8"))
    for sc in scs:
        errs, reply = run(sc)
        print(("PASS" if not errs else "FAIL"), sc["id"], sc["name"])
        if errs:
            fails += 1
            print("   ", errs, "\n    reply:", reply[:300].replace("\n", " "))
    print(f"\n{len(scs) - fails}/{len(scs)} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
