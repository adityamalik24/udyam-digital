"""The web front end: every screen, the checks behind every button, KYC through the job queue, and voice input."""
import io, os, struct, sys, tempfile, time, wave, pathlib
ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "web.db")
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from core import asr, consent, llm
from core.kyc.pipeline import FILES, DATA
import web.server as server

H = {"X-Requested-With": "udyam"}
PLAN = "Clinic in Delhi, 6 staff, one location, have GSTIN, want email"


def client():
    return TestClient(server.app)


def post(c, path, data=None):
    r = c.post(path, json=data if data is not None else {}, headers=H)
    return r


def chat_to_plan(c):
    c.get("/api/view/advisor")
    v = post(c, "/api/advisor/message", {"text": PLAN}).json()
    assert v["has_plan"], v["chat"][-1]
    return v


def add_contact(c, name="Ravi Kumar", phone="9876543210"):
    r = post(c, "/api/contact", {"name": name, "phone": phone, "agree": True})
    assert r.status_code == 200, r.text
    return r.json()


def wait_for_kyc(c, seconds=180):
    end = time.time() + seconds
    while time.time() < end:
        v = c.get("/api/view/kyc").json()
        if not v["job"]["busy"]: return v
        time.sleep(0.3)
    raise AssertionError("KYC job did not finish")


def wav(seconds=1.0, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\0\0" * int(seconds * rate))
    return out.getvalue()


class FakeModels:
    def __init__(self, text): self.text, self.calls = text, []
    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        return type("R", (), {"text": self.text, "function_calls": None})()


class Fake:
    def __init__(self, text): self.models = FakeModels(text)


@pytest.mark.parametrize("page", ["home", "advisor", "quote", "consent", "kyc", "tracker", "data", "partner"])
def test_every_screen_renders_for_a_new_visitor(page):
    v = client().get(f"/api/view/{page}")
    assert v.status_code == 200 and v.json()["nav"]["title"]


@pytest.mark.parametrize("path", ["/", "/advisor", "/quote", "/consent", "/kyc", "/tracker", "/data", "/partner"])
def test_pages_serve_the_app_with_safe_headers(path):
    r = client().get(path)
    assert r.status_code == 200 and "app.js" in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"


def test_unknown_paths_and_api_pages_are_not_found():
    c = client()
    assert c.get("/admin").status_code == 404 and c.get("/api/view/secret").status_code == 404


def test_cookie_is_http_only_and_ids_are_not_chosen_by_the_browser():
    c = client()
    r = c.get("/api/view/home")
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    c2 = TestClient(server.app, cookies={"udyam_sid": "chosen-by-attacker"})
    assert "chosen-by-attacker" not in c2.get("/api/view/home").headers.get("set-cookie", "")


def test_posts_without_the_app_header_are_refused():
    c = client()
    assert c.post("/api/advisor/message", json={"text": "hi"}).status_code == 403


def test_chat_quote_accept_uses_the_server_price_only():
    c = client()
    chat_to_plan(c)
    q = c.get("/api/view/quote").json()
    want = q["monthly"]
    # A price sent from the browser is ignored: only choices are read.
    q2 = post(c, "/api/quote/change", {"action": "alt", "on": False, "monthly": 1, "price": 1}).json()
    assert q2["monthly"] == want
    acc = post(c, "/api/quote/accept", {"monthly": 1}).json()
    assert acc["already"] and acc["accepted"]
    t = c.get("/api/view/tracker").json()
    assert t["ordered"]["monthly"].startswith(f"₹{want:,}")
    # A second tap must not create a second order.
    post(c, "/api/quote/accept")
    assert c.get("/api/view/tracker").json()["orders"] is None


def test_quote_changes_are_checked():
    c = client()
    chat_to_plan(c)
    q = c.get("/api/view/quote").json()
    email = next(l for l in q["lines"] if l["qty_label"])
    v = post(c, "/api/quote/change", {"action": "qty", "product": email["id"], "value": 10 ** 9}).json()
    assert next(l for l in v["lines"] if l["id"] == email["id"])["qty"] == email["max"]  # clamped, not trusted
    assert post(c, "/api/quote/change", {"action": "qty", "product": email["id"], "value": "lots"}).status_code == 400
    assert post(c, "/api/quote/change", {"action": "hack"}).status_code == 400
    removable = next(l for l in v["lines"] if l["remove"])
    gone = post(c, "/api/quote/change", {"action": "remove", "product": removable["id"]}).json()
    assert removable["id"] not in [l["id"] for l in gone["lines"]] and gone["put_back"]
    back = post(c, "/api/quote/change", {"action": "restore"}).json()
    assert removable["id"] in [l["id"] for l in back["lines"]]
    blocked = [a for a in back["addons"] if not a["ok"]]
    if blocked:  # an ineligible add-on can't be switched on from outside
        after = post(c, "/api/quote/change", {"action": "addon", "product": blocked[0]["id"], "on": True}).json()
        assert not next(a for a in after["addons"] if a["id"] == blocked[0]["id"])["on"]


def test_quote_without_a_plan_and_bill_compare():
    c = client()
    assert c.get("/api/view/quote").json()["empty"]
    assert post(c, "/api/quote/accept").status_code == 409
    chat_to_plan(c)
    r = post(c, "/api/quote/compare", {"now": 500}).json()
    assert "more" in r["text"]
    assert c.get("/api/quote/download").text.strip()


def test_orders_belong_to_one_browser():
    a, b = client(), client()
    chat_to_plan(a); post(a, "/api/quote/accept")
    oid = a.get("/api/view/tracker").json()["order"]
    for path, data in [("/api/order/pay", {"order": oid}), ("/api/order/demo", {"order": oid, "action": "advance"}), ("/api/order/reschedule", {"order": oid, "date": "2026-08-01"}), ("/api/tracker/select", {"order": oid})]:
        assert post(b, path, data).status_code == 404, path
    assert post(a, "/api/order/pay", {"order": str(oid)}).status_code == 404  # only a real id, not a string


def test_consent_needs_kyc_and_kyc_needs_consent():
    c = client()
    assert post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K02"}).status_code == 403
    assert c.post("/api/kyc/upload", content=b"x", headers=H).status_code == 403
    assert post(c, "/api/consent", {"updates": True}).status_code == 400  # optional alone isn't enough the first time
    v = post(c, "/api/consent", {"kyc": True}).json()
    assert v["kyc"]["given"] and not v["updates"]["given"]


def test_specimen_kyc_runs_as_a_job_and_unlocks_payment():
    c = client()
    chat_to_plan(c); post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True}); add_contact(c)
    v = post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K02"}).json()
    assert v["job"]["busy"]
    v = wait_for_kyc(c)
    assert v["result"]["verdict"] == "verified" and v["pay"]
    t = c.get("/api/view/tracker").json()
    assert t["pay"] and not t.get("hold")
    assert post(c, "/api/order/pay", {"order": t["order"]}).json()["ok"]
    t = c.get("/api/view/tracker").json()
    assert t["paid_notice"] and not t.get("pay")
    assert post(c, "/api/order/pay", {"order": t["order"]}).status_code == 409  # can't pay twice


def test_rejected_applicant_holds_the_order_and_demo_cannot_skip_it():
    c = client()
    chat_to_plan(c); post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True})
    post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K01"})
    v = wait_for_kyc(c)
    assert v["result"]["verdict"] == "rejected" and not v["pay"]
    t = c.get("/api/view/tracker").json()
    assert t["hold"] and not t.get("pay")
    assert post(c, "/api/order/demo", {"order": t["order"], "action": "advance"}).status_code == 409
    assert post(c, "/api/order/pay", {"order": t["order"]}).status_code == 409
    assert post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K99"}).status_code == 400


def test_uploads_any_order_verify_and_are_dropped():
    c = client()
    post(c, "/api/consent", {"kyc": True})
    for key in ("bill", "id", "gst", "udyam"):  # deliberately out of order
        data = (DATA / "kyc_documents" / f"K03_{FILES[key]}.png").read_bytes()
        assert c.post("/api/kyc/upload", content=data, headers={**H, "X-File-Name": "photo.png"}).json()["pending"]
    bad = c.post("/api/kyc/upload", content=b"not an image", headers={**H, "X-File-Name": "x.png"})
    assert bad.status_code == 400 and "x.png" in bad.json()["problem"]
    assert c.get("/api/view/kyc").json()["pending"] == 4
    post(c, "/api/kyc/verify", {"mode": "upload"})
    v = wait_for_kyc(c)
    assert v["result"]["verdict"] == "verified" and v["pending"] == 0
    assert post(c, "/api/kyc/verify", {"mode": "upload"}).status_code == 400  # nothing kept to verify again


def test_too_many_pages_and_too_big_are_refused():
    c = client()
    post(c, "/api/consent", {"kyc": True})
    page = (DATA / "kyc_documents" / "K03_signatory_id.png").read_bytes()
    for _ in range(8): assert c.post("/api/kyc/upload", content=page, headers=H).status_code == 200
    assert c.post("/api/kyc/upload", content=page, headers=H).status_code == 400
    assert c.delete("/api/kyc/upload", headers=H).json()["ok"]
    big = c.post("/api/kyc/upload", content=b"0" * (11 * 1024 * 1024), headers=H)
    assert big.status_code == 413


def test_withdrawing_kyc_consent_clears_the_result():
    c = client()
    post(c, "/api/consent", {"kyc": True})
    post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K02"}); wait_for_kyc(c)
    assert post(c, "/api/consent/withdraw", {"purpose": consent.KYC}).json()["ok"]
    assert c.get("/api/view/kyc").json()["blocked"]
    post(c, "/api/consent", {"kyc": True})
    assert c.get("/api/view/kyc").json()["result"] is None
    assert post(c, "/api/consent/withdraw", {"purpose": "made_up"}).status_code == 400


def test_lookup_shows_only_status():
    c = client()
    post(c, "/api/consent", {"kyc": True})
    v = post(c, "/api/kyc/lookup", {"gstin": "not a gstin", "udyam": "nope"}).json()
    tones = [n["tone"] for n in v["lookup"]["notices"]]
    assert tones == ["warning", "warning"]


def test_language_switch_and_hindi_screens():
    c = client()
    assert post(c, "/api/language", {"lang": "xx"}).status_code == 400
    post(c, "/api/language", {"lang": "hi"})
    v = c.get("/api/view/advisor").json()
    assert v["lang"] == "hi" and "नमस्ते" in v["chat"][0]["text"]
    assert c.get("/api/view/quote").json()["title"] == "आपका कोटेशन"


def test_short_form_and_callback():
    c = client()
    assert post(c, "/api/advisor/form", {"kind": "clinic", "city": " "}).status_code == 400
    assert post(c, "/api/advisor/form", {"kind": "spaceship", "city": "Delhi"}).status_code == 400
    v = post(c, "/api/advisor/form", {"kind": "clinic", "city": "Delhi", "staff": 6, "sites": 1, "gst": "yes", "needs": ["internet", "cloud_email"]}).json()
    assert v["has_plan"] and v["chat"][0]["role"] == "assistant"
    no = post(c, "/api/advisor/callback", {"phone": "9876543210", "agree": False})
    assert no.status_code == 400 and no.json()["problem"]
    assert post(c, "/api/advisor/callback", {"phone": "123", "agree": True}).status_code == 400
    ok = post(c, "/api/advisor/callback", {"phone": "9876543210", "agree": True, "best": "<script>"}).json()
    assert ok["callback"]["sent"]
    assert not c.delete("/api/advisor/callback", headers=H).json()["callback"]["sent"]


def test_chat_text_is_redacted_before_it_is_shown_back():
    c = client()
    c.get("/api/view/advisor")
    v = post(c, "/api/advisor/message", {"text": "my aadhaar is 1234 5678 9012, I run a kirana in Pune"}).json()
    shown = " ".join(m["text"] for m in v["chat"])
    assert "9012" not in shown


# ---- Voice -----------------------------------------------------------------------------------------------------------
def test_voice_needs_its_own_consent():
    c = client()
    c.get("/api/view/advisor")
    r = c.post("/api/voice", content=wav(), headers={**H, "Content-Type": "audio/wav"})
    assert r.status_code == 403
    assert consent.PURPOSE_LABEL[consent.VOICE]["hi"] and consent.VOICE_NOTICE["hi"]


def test_voice_endpoint_returns_words_for_the_owner_to_check(monkeypatch):
    c = client()
    c.get("/api/view/advisor")
    post(c, "/api/voice/consent")
    fake = Fake("मेरा क्लिनिक है दिल्ली में, 6 staff")
    real = asr.transcribe
    monkeypatch.setattr(server.asr, "transcribe", lambda data, no_ai: real(data, no_ai, c=fake))
    r = c.post("/api/voice", content=wav(), headers={**H, "Content-Type": "audio/wav"}).json()
    assert r["text"] == "मेरा क्लिनिक है दिल्ली में, 6 staff" and not r["removed"]
    # Nothing was added to the chat: the owner sends it.
    assert len(c.get("/api/view/advisor").json()["chat"]) == 1
    assert "voice_input" in [a["purpose"] for a in c.get("/api/view/data").json()["panel"]["active"]]
    post(c, "/api/consent/withdraw", {"purpose": consent.VOICE})
    assert c.post("/api/voice", content=wav(), headers={**H, "Content-Type": "audio/wav"}).status_code == 403


def test_voice_is_rate_limited(monkeypatch):
    c = client()
    post(c, "/api/voice/consent")
    monkeypatch.setattr(server.asr, "transcribe", lambda data, no_ai: {"text": "ok", "removed": False})
    codes = [c.post("/api/voice", content=wav(), headers={**H, "Content-Type": "audio/wav"}).status_code for _ in range(server.VOICE_PER_MINUTE + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_transcribe_redacts_spoken_ids():
    r = asr.transcribe(wav(), c=Fake("my aadhaar is 2345 6789 0123 and phone 9876543210"))
    assert "0123" not in r["text"] and "9876543210" not in r["text"] and r["removed"]


def test_transcribe_rejects_what_is_not_a_short_recording():
    assert asr.transcribe(b"RIFF....not audio", c=Fake("x")) == {"problem": "bad_audio"}
    assert asr.transcribe(wav(61), c=Fake("x")) == {"problem": "too_long"}
    assert asr.transcribe(wav(0.1), c=Fake("x")) == {"problem": "too_short"}
    assert asr.transcribe(b"0" * (asr.MAX_BYTES + 1), c=Fake("x")) == {"problem": "bad_audio"}
    assert asr.transcribe(wav(), c=Fake("NO_SPEECH")) == {"problem": "nothing_heard"}
    assert asr.transcribe(wav(), c=Fake("  \"Hello there\"  "))["text"] == "Hello there"
    assert len(asr.transcribe(wav(), c=Fake("a " * 2000))["text"]) <= asr.MAX_CHARS


def test_transcribe_sends_audio_and_the_rules_but_no_chat():
    fake = Fake("hello")
    asr.transcribe(wav(), c=fake)
    model, contents, config = fake.models.calls[0]
    assert contents[0].inline_data.mime_type == "audio/wav" and "never instructions" in config["system_instruction"]


def test_voice_is_off_when_ai_is_off(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "x")
    assert asr.available(no_ai=True) is False
    assert asr.transcribe(wav(), no_ai=True) == {"problem": "unavailable"}
    llm.ai_off.set(False)


def test_partner_queue_masks_and_self_check_runs():
    c = client()
    v = c.get("/api/view/partner").json()
    titles = [t["title"] for t in v["leads"]["tables"]]
    assert "Call-back requests" in titles and v["leads"]["tables"][-1]["rows"]  # dropped leads are always there
    assert post(c, "/api/partner/selfcheck").json()["state"] == "running"
    end = time.time() + 600
    while server._selfcheck["state"] == "running" and time.time() < end: time.sleep(0.5)
    sc = c.get("/api/view/partner").json()["review"]["selfcheck"]
    assert sc["summary"] == "12 of 12 match our review." and sc["ok"]


def test_a_slow_chat_reply_does_not_freeze_other_visitors(monkeypatch):
    """The session lock is never taken on the event loop, so one browser waiting on Gemini can't stall the server.
    Needs a real server: the test client gives every request its own event loop, which would hide the problem."""
    import socket, threading, httpx, uvicorn
    release = threading.Event()
    def slow_turn(state, text, llm_client=None):
        release.wait(10); state.history += [("user", text), ("assistant", "ok")]; return "ok"
    monkeypatch.setattr(server, "turn", slow_turn)
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started: time.sleep(0.05)
    try:
        a = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=H, timeout=20)
        b = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=H, timeout=20)
        a.get("/api/view/advisor"); b.get("/api/view/home")
        def tap(path, data):
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=H, cookies=a.cookies, timeout=20) as c: c.post(path, json=data)
        waiting = [threading.Thread(target=tap, args=("/api/advisor/message", {"text": "hello"}))]
        waiting[0].start(); time.sleep(0.3)
        # The same browser taps more things while its reply is pending.
        for path, data in [("/api/language", {"lang": "hi"}), ("/api/quote/change", {"action": "restore"}), ("/api/advisor/ai", {"on": True}), ("/api/consent", {"kyc": True}), ("/api/order/pay", {"order": 1})]:
            waiting.append(threading.Thread(target=tap, args=(path, data))); waiting[-1].start()
        time.sleep(0.5)
        started = time.time()
        assert b.get("/api/view/home").status_code == 200
        assert time.time() - started < 2, "another visitor was held up"
    finally:
        release.set()
        for t in waiting: t.join(15)
        srv.should_exit = True


# ---- Ported from the Streamlit app: dashboard, A/B, peers, bill snap, rights, reviews, signals ---------------------------
def test_funnel_events_and_ab_variant_flow_through(monkeypatch, tmp_path):
    from core import db, events
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "web_events.db")
    c = client()
    chat_to_plan(c)
    from web import session as web_session
    s = web_session._sessions[c.cookies["udyam_sid"]]  # this browser's own session, not just any with a plan
    q = c.get("/api/view/quote").json()
    assert (q["per_day"] is not None) == (s.ab == "B")
    assert any(l["peers"] for l in q["lines"]) and "professional offices customers" in next(l["peers"] for l in q["lines"] if l["peers"])
    post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True}); add_contact(c)
    post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K02"}); wait_for_kyc(c)
    t = c.get("/api/view/tracker").json(); post(c, "/api/order/pay", {"order": t["order"]})
    reached = {x["step"]: x["count"] for x in events.funnel()}
    assert all(reached[k] == 1 for k in ("Chat started", "Plan shown", "Quote viewed", "Quote accepted", "KYC consent given", "KYC result", "Paid"))
    assert events.ab_test()["arms"][s.ab]["accepted"] == 1
    assert t.get("past") and "days from first contact" in t["past"]


def test_bill_snap_reads_the_amount_and_needs_a_plan():
    c = client()
    bill = (DATA / "kyc_documents" / "K03_address_proof.png").read_bytes()
    assert c.post("/api/quote/bill", content=bill, headers=H).status_code == 409
    chat_to_plan(c)
    assert c.post("/api/quote/bill", content=bill, headers=H).json() == {"amount": 33615}
    assert c.post("/api/quote/bill", content=b"junk", headers=H).json() == {"amount": None}
    assert c.post("/api/quote/bill", content=bill).status_code == 403  # the app header is still required


def test_json_receipt_export_correction_and_erase():
    c = client()
    chat_to_plan(c); post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True, "updates": True})
    rj = c.get("/api/consent/receipt.json")
    assert rj.headers["content-type"].startswith("application/json") and rj.json()["jurisdiction"] == "IN"
    assert c.get("/api/view/data").json()["panel"]["receipt_json"]
    data = c.get("/api/data/export").json()
    assert len(data["orders"]) == 1 and len(data["consents"]) == 2
    assert post(c, "/api/data/correction", {"detail": " "}).status_code == 400
    assert post(c, "/api/data/correction", {"detail": "City is Pune"}).json()["ok"]
    assert post(c, "/api/data/erase", {"sure": False}).status_code == 400
    assert post(c, "/api/data/erase", {"sure": True}).json()["ok"]
    after = c.get("/api/data/export").json()
    assert after["orders"] == [] and after["consents"] == [] and after["reference"] != data["reference"]  # a fresh identity
    assert c.get("/api/view/advisor").json()["chat"][0]["role"] == "assistant" and len(c.get("/api/view/advisor").json()["chat"]) == 1


def test_partner_tabs_and_maker_checker_review():
    owner, staff = client(), client()
    chat_to_plan(owner); post(owner, "/api/quote/accept"); post(owner, "/api/consent", {"kyc": True}); add_contact(owner)
    post(owner, "/api/kyc/verify", {"mode": "specimen", "applicant": "K04"})
    assert wait_for_kyc(owner)["result"]["verdict"] == "needs_review"
    v = staff.get("/api/view/partner").json()
    assert [t["key"] for t in v["tabs"]] == ["dash", "review", "leads", "money", "logs", "evidence"]
    assert v["dash"]["tables"][1]["title"] == "Against the deck's targets" and v["leads"]["tables"][3]["headers"][-1] == "Send"
    case = v["review"]["open_cases"][0]
    assert post(staff, "/api/partner/review/propose", {"case": case, "decision": "verified", "note": "", "maker": "Asha"}).json()["problem"]
    assert post(staff, "/api/partner/review/propose", {"case": case, "decision": "verified", "note": "Re-checked the GST certificate by hand", "maker": "Asha"}).json()["ok"]
    rid = staff.get("/api/view/partner").json()["review"]["pending"][0]["id"]
    assert "different" in post(staff, "/api/partner/review/confirm", {"id": rid, "checker": "ASHA", "accept": True}).json()["problem"]
    assert post(staff, "/api/partner/review/confirm", {"id": rid, "checker": "Ravi", "accept": True}).json()["ok"]
    k = owner.get("/api/view/kyc").json()
    assert k["reviewed"]["tone"] == "success" and k["result"] is None and k["pay"]
    assert owner.get("/api/view/tracker").json()["pay"]


def test_whatif_matches_the_deck_and_clamps_inputs():
    c = client()
    base = c.get("/api/partner/whatif", params={"segment": "Micro retail & services"}).json()
    assert base["metrics"][1]["value"] == "8.0" and base["metrics"][1]["delta"] is None
    moved = c.get("/api/partner/whatif", params={"segment": "Micro retail & services", "share": 0.5}).json()
    assert float(moved["metrics"][1]["value"]) < 8 and moved["metrics"][1]["delta"].startswith("-")
    wild = c.get("/api/partner/whatif", params={"segment": "nonsense", "share": 9, "price": 9, "churn": -9}).json()
    assert wild["segment"] == "Micro retail & services"


def test_upload_signals_reach_the_reviewer_but_not_the_verdict():
    from PIL import PngImagePlugin
    c = client()
    post(c, "/api/consent", {"kyc": True})
    for key in ("gst", "udyam", "id", "bill"):
        img = Image.open(DATA / "kyc_documents" / f"K03_{FILES[key]}.png")
        info = PngImagePlugin.PngInfo()
        if key == "gst": info.add_text("Software", "Adobe Photoshop")
        b = io.BytesIO(); img.save(b, "PNG", pnginfo=info)
        c.post("/api/kyc/upload", content=b.getvalue(), headers=H)
    post(c, "/api/kyc/verify", {"mode": "upload"})
    assert wait_for_kyc(c)["result"]["verdict"] == "verified"  # a signal never changes the verdict
    import json as _json
    last = consent.latest_kyc(c.get("/api/data/export").json()["reference"])
    assert _json.loads(last["fields"])["signals"][0]["code"] == "editor_software"


def test_specimen_docs_listed_with_names_and_k05_note():
    c = client(); post(c, "/api/consent", {"kyc": True})
    v = c.get("/api/view/kyc").json()
    assert len(v["specimen_docs"]["K05"]) == 3 and len(v["specimen_docs"]["K02"]) == 4 and v["only_these"]


# ---- UI changes: AI notice moved, person panel, quote chat, live language switch, new chat --------------------------------
def test_ai_notice_lives_on_the_data_page_with_its_switch():
    c = client()
    v = c.get("/api/view/advisor").json()
    assert "ai" not in v and v["ai_line"]  # no dropdown in the chat, just a one-line pointer
    d = c.get("/api/view/data").json()
    assert d["ai"]["on"] and "Gemini" in d["ai"]["body"]
    post(c, "/api/advisor/ai", {"on": False})
    assert not c.get("/api/view/data").json()["ai"]["on"] and c.get("/api/view/advisor").json()["voice"]["ai_off"]


def test_talk_to_a_person_is_always_available_and_flags_a_hand_off():
    c = client()
    v = c.get("/api/view/advisor").json()
    assert v["callback"] and not v["callback"]["alert"]
    v = post(c, "/api/advisor/message", {"text": "this is useless, let me talk to a human"}).json()
    assert v["callback"]["alert"]


def test_quote_page_carries_the_chat_and_a_change_there_updates_the_quote():
    c = client()
    chat_to_plan(c)
    q = c.get("/api/view/quote").json()
    advisor = c.get("/api/view/advisor").json()
    assert [m["text"] for m in q["chat"]["messages"]] == [m["text"] for m in advisor["chat"]]
    names = [l["name"] for l in q["lines"]]
    assert "Endpoint Security" in names
    post(c, "/api/advisor/message", {"text": "remove security"})
    after = c.get("/api/view/quote").json()
    assert "Endpoint Security" not in [l["name"] for l in after["lines"]] and after["monthly"] < q["monthly"]
    assert len(after["chat"]["messages"]) == len(q["chat"]["messages"]) + 2


def _fake_translation(monkeypatch, result=lambda text, lang: (f"[{lang}] {text}", "ok")):
    import core.advisor
    monkeypatch.setattr(server.V, "_can_translate", lambda s: True)
    monkeypatch.setattr(core.advisor, "translate_reply", result)


def test_language_switch_translates_what_was_on_screen(monkeypatch):
    _fake_translation(monkeypatch)
    c = client()
    chat_to_plan(c)
    before = c.get("/api/view/advisor").json()["chat"]
    post(c, "/api/language", {"lang": "hi"})
    v = c.get("/api/view/advisor").json()
    assert v["lang"] == "hi" and v["translate"] and "नमस्ते" in v["chat"][0]["text"]  # the welcome is redrawn at once
    assert v["chat"][1]["text"] == before[1]["text"]  # what the owner typed is never changed
    assert v["chat"][2]["translating"]
    post(c, "/api/advisor/translate")
    v = c.get("/api/view/advisor").json()
    assert not v["translate"] and v["chat"][2]["text"] == "[hi] " + before[2]["text"] and not v["chat"][2]["translating"]
    assert c.get("/api/view/quote").json()["chat"]["messages"][2]["text"].startswith("[hi] ")
    reply = post(c, "/api/advisor/message", {"text": "ठीक है"}).json()["chat"][-1]["text"]
    assert not reply.startswith("[hi]")  # replies after the switch are written in Hindi, not translated
    post(c, "/api/language", {"lang": "en"})
    back = c.get("/api/view/advisor").json()
    assert back["chat"][2]["text"] == before[2]["text"]  # English originals come straight back


def test_failed_or_unavailable_translation_keeps_the_original(monkeypatch):
    _fake_translation(monkeypatch, lambda text, lang: (None, "refused"))
    c = client(); chat_to_plan(c)
    post(c, "/api/language", {"lang": "hi"}); post(c, "/api/advisor/translate")
    v = c.get("/api/view/advisor").json()
    assert not v["translate"] and v["kept"] and not any(m.get("translating") for m in v["chat"])  # no endless retries
    monkeypatch.setattr(server.V, "_can_translate", lambda s: False)
    c2 = client(); chat_to_plan(c2); post(c2, "/api/language", {"lang": "hi"})
    v2 = c2.get("/api/view/advisor").json()
    assert not v2["translate"] and v2["kept"]


def test_hinglish_written_on_an_english_page_is_not_translated(monkeypatch):
    _fake_translation(monkeypatch)
    c = client(); c.get("/api/view/advisor")
    v = post(c, "/api/advisor/message", {"text": "mera kirana store hai Jaipur mein, 2 log kaam karte hain"}).json()
    assert v["lang"] == "en" and not v["translate"] and not v["chat"][-1]["text"].startswith("[")


def test_new_chat_starts_fresh_from_anywhere():
    c = client()
    chat_to_plan(c)
    assert c.get("/api/view/quote").json()["nav"]["new_chat"]
    post(c, "/api/advisor/new")
    v = c.get("/api/view/advisor").json()
    assert len(v["chat"]) == 1 and not v["has_plan"] and c.get("/api/view/quote").json()["empty"]


def test_translate_reply_keeps_every_number_and_name():
    from core.advisor import translate_reply
    reply = "- Biz Fibre 100: ₹1,099\n**₹2,671 per month** · setup ₹1,000"
    class Echo:  # a model that translates words but copies slots, as instructed
        def __init__(self, out): self.models = type("M", (), {"generate_content": lambda _s, model, contents, config: type("R", (), {"text": out(contents), "function_calls": None})()})()
    good = translate_reply(reply, "hi", Echo(lambda c: c.split("MESSAGE:\n", 1)[1].split("\n\nYour last")[0].replace("per month", "प्रति माह").replace("setup", "सेटअप")))
    assert good == ("- Biz Fibre 100: ₹1,099\n**₹2,671 प्रति माह** · सेटअप ₹1,000", "ok")
    assert translate_reply(reply, "hi", Echo(lambda c: "सब कुछ ₹999 में")) == (None, "refused")  # an invented amount is refused every time, so the original stays
    assert translate_reply(reply, "hi", Echo(lambda c: None)) == (None, "unavailable")


def test_a_busy_model_is_retried_later_not_given_up(monkeypatch):
    _fake_translation(monkeypatch, lambda text, lang: (None, "unavailable"))
    c = client(); chat_to_plan(c)
    post(c, "/api/language", {"lang": "hi"}); post(c, "/api/advisor/translate")
    v = c.get("/api/view/advisor").json()
    assert not v["translate"]  # resting: no request loop
    monkeypatch.setattr(server.V, "RETRY_TRANSLATION_SECONDS", -1)  # a minute later
    _fake_translation(monkeypatch)
    assert c.get("/api/view/advisor").json()["translate"]
    post(c, "/api/advisor/translate")
    assert c.get("/api/view/advisor").json()["chat"][2]["text"].startswith("[hi] ")



# ---- Contact step and grouped logs -------------------------------------------------------------------------------------
def test_contact_details_need_their_own_consent_and_valid_values():
    c = client()
    assert post(c, "/api/contact", {"name": "Ravi", "phone": "9876543210"}).status_code == 400  # box not ticked
    assert "name" in post(c, "/api/contact", {"name": "1", "phone": "9876543210", "agree": True}).json()["problem"]
    assert "mobile" in post(c, "/api/contact", {"name": "Ravi", "phone": "12345", "agree": True}).json()["problem"]
    v = add_contact(c, "  Ravi   Kumar ", "+91 98765-43210")
    assert v["contact"]["saved"] == {"name": "Ravi Kumar", "phone": "9876543210"}
    assert "service_contact" in [a["purpose"] for a in v["panel"]["active"]]
    v = post(c, "/api/contact", {"name": "Ravi K", "phone": "9123456780"}).json()  # changing them needs no second tick
    assert v["contact"]["saved"]["phone"] == "9123456780"
    assert c.get("/api/view/advisor").json()["callback"]["prefill"] == {"name": "Ravi K", "phone": "9123456780"}


def test_payment_waits_for_contact_details():
    c = client()
    chat_to_plan(c); post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True})
    post(c, "/api/kyc/verify", {"mode": "specimen", "applicant": "K02"})
    k = wait_for_kyc(c)
    assert k["pay"] is None and k["need_contact"]
    t = c.get("/api/view/tracker").json()
    assert not t.get("pay") and t["need_contact"]
    assert post(c, "/api/order/pay", {"order": t["order"]}).status_code == 409
    add_contact(c)
    assert c.get("/api/view/kyc").json()["pay"] and post(c, "/api/order/pay", {"order": t["order"]}).json()["ok"]


def test_withdrawing_or_erasing_deletes_contact_details():
    c = client(); add_contact(c, "Asha", "9111122223")  # a number no other test uses
    assert c.get("/api/data/export").json()["contact_details"]["phone"] == "9111122223"
    post(c, "/api/consent/withdraw", {"purpose": consent.CONTACT})
    assert c.get("/api/view/consent").json()["contact"]["saved"] is None and c.get("/api/data/export").json()["contact_details"] is None
    add_contact(c, "Asha", "9111122223"); post(c, "/api/data/erase", {"sure": True})
    from core import db
    with db.conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM contacts WHERE phone='9111122223'").fetchone()[0] == 0


def test_logs_are_grouped_by_customer_with_masked_contact():
    a, b, staff = client(), client(), client()
    add_contact(a, "Meena Shah", "9000011111"); post(a, "/api/consent", {"kyc": True})
    post(b, "/api/consent", {"kyc": True})
    logs = staff.get("/api/view/partner").json()["logs"]
    ref_a = "…" + a.get("/api/data/export").json()["reference"][-4:]
    g = next(x for x in logs["groups"] if x["ref"] == ref_a)
    assert g["who"] == "M… · ••••••1111" and g["count"] == 3
    assert [x["action"] for x in g["steps"]] == ["Gave consent", "Saved contact details", "Gave consent"]
    assert "9000011111" not in str(logs) and "Meena" not in str(logs)


def test_staff_passcode_locks_partner_pages_only_when_set(monkeypatch):
    c = client()
    monkeypatch.delenv("PARTNER_PASSCODE", raising=False)
    assert c.get("/api/view/partner").status_code == 200  # unset: open, as on a laptop
    monkeypatch.setenv("PARTNER_PASSCODE", "staff-2026")
    monkeypatch.setattr(server, "_staff_fails", [])
    c2 = client()
    r = c2.get("/api/view/partner")
    assert r.status_code == 401 and r.json()["error"] == "staff_only"
    assert c2.get("/api/partner/whatif?segment=micro").status_code == 401
    assert post(c2, "/api/partner/selfcheck").status_code == 401
    assert c2.get("/api/view/advisor").status_code == 200  # customer pages are never locked
    assert post(c2, "/api/staff/login", {"code": "wrong"}).status_code == 401
    assert c2.get("/api/view/partner").status_code == 401
    assert post(c2, "/api/staff/login", {"code": "staff-2026"}).status_code == 200
    assert c2.get("/api/view/partner").status_code == 200
    assert client().get("/api/view/partner").status_code == 401  # another browser still needs it


def test_staff_passcode_limits_wrong_tries(monkeypatch):
    monkeypatch.setenv("PARTNER_PASSCODE", "staff-2026")
    monkeypatch.setattr(server, "_staff_fails", [])
    c = client()
    for _ in range(server.STAFF_TRIES_PER_MINUTE): assert post(c, "/api/staff/login", {"code": "nope"}).status_code == 401
    assert post(c, "/api/staff/login", {"code": "staff-2026"}).status_code == 429  # even the right one waits


def test_ab_test_can_be_switched_off(monkeypatch):
    from web import session
    monkeypatch.setenv("AB_TEST", "off")
    assert {session.Session().ab for _ in range(40)} == {"A"}
    monkeypatch.setenv("AB_TEST", "on")
    assert {session.Session().ab for _ in range(60)} == {"A", "B"}


def test_no_gstin_tick_on_a_plan_that_needs_none():
    def start():
        c = client(); c.get("/api/view/advisor")
        v = post(c, "/api/advisor/message", {"text": "Kirana store in Delhi, 2 staff, 1 shop, no GST, need internet for UPI"}).json()
        assert v["has_plan"], v["chat"][-1]
        assert post(c, "/api/quote/accept").status_code == 200
        post(c, "/api/consent", {"kyc": True})
        for key in ("id", "bill"):
            c.post("/api/kyc/upload", content=(DATA / "kyc_documents" / f"K03_{FILES[key]}.png").read_bytes(), headers={**H, "X-File-Name": "p.png"})
        return c
    c = start()
    assert c.get("/api/view/kyc").json()["no_gstin_label"]
    post(c, "/api/kyc/verify", {"mode": "upload", "no_gstin": True})
    assert wait_for_kyc(c)["result"]["verdict"] == "verified"
    c = start()
    post(c, "/api/kyc/verify", {"mode": "upload"})
    r = wait_for_kyc(c)["result"]
    assert r["verdict"] == "needs_review" and "wasn't ticked" in r["reason"]


def test_no_gstin_tick_is_not_offered_when_the_plan_needs_a_gstin():
    c = client(); c.get("/api/view/advisor")
    assert post(c, "/api/advisor/message", {"text": "CA firm Mumbai 12 staff 1 office GST yes, want a toll free number so customers can call me"}).json()["has_plan"]
    post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True})  # a toll-free number is sold only with a GSTIN
    v = c.get("/api/view/kyc").json()
    assert "upload_intro" in v and v["no_gstin_label"] is None and v["no_gst"] is None


def test_installable_on_phones_and_caches_nothing():
    import json as _json
    c = client()
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"] and "udyam_sid" not in sw.headers.get("set-cookie", "")
    assert "caches." not in sw.text and "cache.put" not in sw.text  # nothing about a chat, quote or document is kept on the phone
    m = c.get("/static/manifest.json")
    man = _json.loads(m.text)
    assert m.status_code == 200 and man["display"] == "standalone" and man["start_url"] == "/"
    for icon in man["icons"]: assert c.get(icon["src"]).status_code == 200
    page = c.get("/").text
    assert 'rel="manifest"' in page and "apple-touch-icon" in page
    assert "Airtel" not in page + m.text  # fictional brand only


def test_ai_line_says_what_really_happens(monkeypatch):
    c = client(); c.get("/api/view/advisor")
    monkeypatch.setattr(llm, "client", lambda: None)
    assert "without AI" in c.get("/api/view/advisor").json()["ai_line"]  # no key on the server: nothing goes to Gemini
    monkeypatch.setattr(llm, "client", lambda: object())
    assert c.get("/api/view/advisor").json()["ai_line"].startswith("Replies are written with AI")
    post(c, "/api/advisor/ai", {"on": False})
    assert "You turned AI off" in c.get("/api/view/advisor").json()["ai_line"]


def _owner_with_order(phone="9123456780"):
    a = client(); chat_to_plan(a); assert post(a, "/api/quote/accept").status_code == 200
    add_contact(a, "Asha Rao", phone)
    oid = a.get("/api/view/tracker").json()["order"]
    return a, oid


def test_find_my_order_from_another_browser(monkeypatch):
    monkeypatch.setattr(server, "_finds", [])
    a, oid = _owner_with_order("9123456780")
    assert f"Order number {oid}" in a.get("/api/view/tracker").json()["order_no"]
    b = client()
    v = b.get("/api/view/tracker").json()
    assert v["empty"] and v["find"]["title"] == "Find my order"
    assert post(b, "/api/track/find", {"order": oid, "phone": "9123456789"}).status_code == 404  # wrong mobile
    assert post(b, "/api/track/find", {"order": "", "phone": "123"}).status_code == 400
    r = post(b, "/api/track/find", {"order": f"#{oid}", "phone": "+91 91234 56780"}).json()
    assert r["code_sent"] and r["to"] == "••••••6780" and len(r["demo_code"]) == 6
    wrong = "000000" if r["demo_code"] != "000000" else "111111"
    assert "isn't right" in post(b, "/api/track/verify", {"code": wrong}).json()["problem"]
    assert b.get("/api/view/tracker").json().get("empty")  # nothing opens before the right code
    assert post(b, "/api/track/verify", {"code": r["demo_code"]}).json()["done"]
    t = b.get("/api/view/tracker").json()
    assert t["order"] == oid and not t.get("empty")
    assert post(b, "/api/track/verify", {"code": r["demo_code"]}).status_code == 400  # a code works once


def test_find_my_order_limits_and_consent(monkeypatch):
    from core import find_order
    monkeypatch.setattr(server, "_finds", [])
    a, oid = _owner_with_order("9988776655")
    b = client()
    for _ in range(find_order.MAX_FINDS): post(b, "/api/track/find", {"order": oid + 999, "phone": "9988776655"})
    assert post(b, "/api/track/find", {"order": oid, "phone": "9988776655"}).status_code == 429  # even the right details wait
    c = client()
    code = post(c, "/api/track/find", {"order": oid, "phone": "9988776655"}).json()["demo_code"]
    bad = "000000" if code != "000000" else "111111"
    for _ in range(find_order.MAX_CODE_TRIES): post(c, "/api/track/verify", {"code": bad})
    assert post(c, "/api/track/verify", {"code": code}).status_code == 400  # three wrong tries burn the code
    post(a, "/api/consent/withdraw", {"purpose": consent.CONTACT})
    assert post(client(), "/api/track/find", {"order": oid, "phone": "9988776655"}).status_code == 404  # contact consent withdrawn: not findable


def test_find_order_code_expires():
    from core import find_order
    p = find_order.new_code("demo-x", 1, now=1000.0)
    assert find_order.check(p, p["code"], now=1000.0 + find_order.CODE_SECONDS + 1) == "expired"
    q = find_order.new_code("demo-x", 1, now=1000.0)
    assert find_order.check(q, q["code"], now=1001.0) == "ok"
    assert find_order.check(None, "123456") == "expired"


def test_footer_switches_between_customer_and_staff():
    c = client()
    assert c.get("/api/view/advisor").json()["nav"]["switch_to"] == "/partner"
    assert c.get("/api/view/partner").json()["nav"]["switch_to"] == "/advisor"


def test_red_team_probes_all_hold(monkeypatch):
    sys.path.insert(0, str(ROOT / "tests"))
    import red_team
    monkeypatch.setattr(server, "_finds", [])
    monkeypatch.setattr(server, "_staff_fails", [])
    monkeypatch.delenv("PARTNER_PASSCODE", raising=False)
    rows = red_team.probes()
    failed = [r[0] for r in rows if not r[2]]
    assert len(rows) >= 28 and not failed, failed


def test_evidence_tab_reruns_checks_in_a_separate_process(monkeypatch):
    monkeypatch.setattr(server, "EVIDENCE", [("Security probes (red team)", ["tests/red_team.py"])])
    monkeypatch.setattr(server, "_evidence", {"state": "idle", "done": 0, "rows": []})
    c = client()
    v = c.get("/api/view/partner").json()
    assert any(t["key"] == "evidence" for t in v["tabs"]) and v["evidence"]["state"] == "idle" and v["evidence"]["kyc"]["title"]
    assert post(c, "/api/partner/evidence").json()["state"] == "running"
    end = time.time() + 240
    while server._evidence["state"] == "running" and time.time() < end: time.sleep(1)
    e = c.get("/api/view/partner").json()["evidence"]
    assert e["state"] == "done" and e["ok"] and e["rows"][0][1].startswith("✓ ") and "attack probes held" in e["rows"][0][1], e
    monkeypatch.setattr(server, "EVIDENCE", [("Missing", ["tests/not_there.py"])])
    assert c.get("/api/view/partner").json()["evidence"]["unavailable"] and post(c, "/api/partner/evidence").status_code == 409
