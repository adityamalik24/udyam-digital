"""The web front end: every screen, the checks behind every button, KYC through the job queue, and voice input."""
import io, os, struct, sys, tempfile, time, wave, pathlib
ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
os.environ["UDYAM_DB"] = os.path.join(tempfile.mkdtemp(), "web.db")
import pytest
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
    chat_to_plan(c); post(c, "/api/quote/accept"); post(c, "/api/consent", {"kyc": True})
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
    titles = [s["title"] for s in v["sections"]]
    assert "Call-back requests" in titles and v["sections"][-1]["rows"]
    assert post(c, "/api/partner/selfcheck").json()["state"] == "running"
    end = time.time() + 600
    while server._selfcheck["state"] == "running" and time.time() < end: time.sleep(0.5)
    sc = c.get("/api/view/partner").json()["selfcheck"]
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
