"""The mobile website: a JSON API over core/ plus a static page. Decisions stay in core/; this file checks who may do what."""
from __future__ import annotations
import hmac, io, json, os, re, subprocess, sys, tempfile, threading, time
from datetime import date
from pathlib import Path
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from core import asr, billscan, callback, consent, contacts, db, find_order, orders, retention, reviews, rights
from core.kyc import forensics
from core.advisor import State, from_form, quick_replies, turn
from core.catalogue import catalogue
from core.kyc import pipeline as KP
from core.kyc.pipeline import FILES, MAX_PAGES, MAX_UPLOAD_MB, SPECIMEN_REVIEW, OcrUnavailable
from core.pricing import summary_text
from core.rules import ADJUSTABLE_UNITS, MAX_QTY, Profile
from . import views as V
from .session import COOKIE, MAX_PENDING_BYTES, Session, get_or_create, pending_bytes, reset

STATIC = Path(__file__).parent / "static"
SCORES = Path(__file__).parent / "lead_scores.json"  # scored once while the image is built, so the small server doesn't load scikit-learn
PAGES = {"/", "/advisor", "/quote", "/consent", "/kyc", "/tracker", "/data", "/partner"}
VOICE_PER_MINUTE = 6
MAX_WAITING = 3  # document checks waiting for the one that's running
CSP = "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
app = FastAPI(title="Udyam Digital", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_ocr_slot = threading.Semaphore(1)  # OCR is the heavy part: one at a time keeps a small server alive
_decode_slot = threading.Semaphore(1)  # and so is opening a big photo
_waiting = 0
_waiting_guard = threading.Lock()
_selfcheck: dict = {"state": "idle", "done": 0, "rows": []}
ROOT = Path(__file__).resolve().parents[1]
# Evidence for judges: the same checks CI runs, rerun on demand. Each runs in its own process with a throwaway database
# and no LLM key, so the live app's data and quota are never touched.
EVIDENCE = [("Advisor scenarios: main set", ["tests/run_scenarios.py", "tests/advisor_scenarios.yaml"]),
            ("Advisor scenarios: development set", ["tests/run_scenarios.py", "tests/advisor_dev.yaml"]),
            ("Advisor scenarios: unseen set", ["tests/run_scenarios.py", "tests/advisor_unseen.yaml"]),
            ("Advisor scenarios: teammate set", ["tests/run_scenarios.py", "tests/advisor_teammate.yaml"]),
            ("Security probes (red team)", ["tests/red_team.py"])]
EVIDENCE_TIMEOUT = 900
_evidence: dict = {"state": "idle", "done": 0, "rows": []}
STAFF_PATHS = ("/api/partner/", "/api/view/partner")
STAFF_TRIES_PER_MINUTE = 10  # wrong passcodes across everyone, so it can't be guessed quickly
_staff_fails: list = []
_staff_guard = threading.Lock()


def staff_code() -> str:
    """PARTNER_PASSCODE locks the staff pages. Unset, they stay open, which is only fine on your own computer."""
    return os.environ.get("PARTNER_PASSCODE", "").strip()


@app.middleware("http")
async def attach_session(request: Request, call_next):
    if request.url.path in ("/healthz", "/sw.js") or request.url.path.startswith("/static"):
        response = await call_next(request)
    else:
        sid, s, new = get_or_create(request.cookies.get(COOKIE))
        request.state.s, request.state.sid = s, sid
        if request.url.path.startswith("/api") and request.method != "GET" and request.headers.get("x-requested-with") != "udyam":
            return JSONResponse({"error": "forbidden"}, 403)  # another site's form can't set this header
        if staff_code() and request.url.path.startswith(STAFF_PATHS) and not s.staff:
            return JSONResponse({"error": "staff_only", "problem": "This page is for Accel Business staff. Please enter the staff passcode."}, 401)
        response = await call_next(request)
        if new:
            await run_in_threadpool(retention.run_once)
            response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=request.headers.get("x-forwarded-proto") == "https", max_age=86400, path="/")
    response.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Permissions-Policy": "microphone=(self), camera=()"})
    if request.url.path.startswith("/api"): response.headers["Cache-Control"] = "no-store"
    return response


def sess(request: Request) -> Session:
    return request.state.s


async def read_limited(request: Request, limit: int) -> bytes:
    """The body, in memory only, refused as soon as it passes the limit."""
    if int(request.headers.get("content-length") or 0) > limit: raise HTTPException(413, "too_big")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit: raise HTTPException(413, "too_big")
    return bytes(data)


async def body(request: Request) -> dict:
    try:
        out = json.loads(await read_limited(request, 64 * 1024) or b"{}")
    except ValueError:
        raise HTTPException(400, "bad_json")
    if not isinstance(out, dict): raise HTTPException(400, "bad_json")
    return out


def own_order(s: Session, oid) -> dict:
    """An order id from the browser is only ever used after checking it belongs to this browser."""
    if not isinstance(oid, int) or oid not in orders.for_user(s.user): raise HTTPException(404, "no_order")
    return orders.get(oid)


# ---- Screens -------------------------------------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/view/{page}")
def view(page: str, request: Request):
    s = sess(request)
    if page == "partner": return V.partner(lead_scores(), selfcheck_view(), evidence_view())
    fn = {"home": V.home, "advisor": V.advisor, "quote": V.quote, "consent": V.consent_page, "kyc": V.kyc, "tracker": V.tracker, "data": V.data_page}.get(page)
    if not fn: raise HTTPException(404)
    with s.lock:
        return fn(s)


@app.post("/api/language")
async def language(request: Request):
    """Switches the whole page, and the advisor's next replies, to English or Hindi. Earlier replies are translated by
    /api/advisor/translate, which the page calls straight after."""
    s, d = sess(request), await body(request)
    if d.get("lang") not in ("en", "hi"): raise HTTPException(400)
    def work():
        with s.lock:
            s.ui_lang = s.synced_lang = d["lang"]
            s.advisor.profile.language, s.advisor.reply_lang = d["lang"], None
            s.switched_before = len(s.chat)
        return {"ok": True}
    return await run_in_threadpool(work)


@app.post("/api/advisor/translate")
def advisor_translate(request: Request):
    s = sess(request)
    with s.lock:
        V.translate_chat(s)
    return {"ok": True}


# ---- Advisor -------------------------------------------------------------------------------------------------------
@app.post("/api/advisor/message")
async def advisor_message(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            a = s.advisor
            text = d.get("text") if isinstance(d.get("text"), str) else None
            if "chip" in d: text = dict(quick_replies(a)).get(d["chip"])
            if not text or not text.strip(): raise HTTPException(400, "empty")
            reply = turn(a, text.strip()[:2000])
            # Only the redacted form of what the owner typed is kept, so identifiers vanish from the transcript too.
            if getattr(a, "restarted", False):
                s.chat, s.tr, s.switched_before = [{"role": "assistant", "text": reply, "lang": a.reply_lang or a.profile.language}], {}, 0; s.addons = set()
            else:
                V.ensure_welcome(s)
                V.add_turn(s, a.history[-2][1], reply)
            V.track_chat(s)
            return V.advisor(s)
    return await run_in_threadpool(work)


@app.post("/api/advisor/new")
def advisor_new(request: Request):
    s = sess(request)
    with s.lock:  # clears the answers and the quote, keeps the language. An accepted order stays in the tracker.
        s.advisor = State(profile=Profile(language=s.advisor.profile.language)); s.chat, s.tr, s.switched_before = [], {}, 0; s.addons = set()
        return V.advisor(s)


@app.post("/api/advisor/ai")
async def advisor_ai(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            s.advisor.no_ai = not bool(d.get("on"))
            return V.advisor(s)
    return await run_in_threadpool(work)


@app.post("/api/advisor/form")
async def advisor_form(request: Request):
    s, d = sess(request), await body(request)
    def number(key, low, high):
        try: return max(low, min(high, int(d.get(key, low))))
        except (TypeError, ValueError): raise HTTPException(400, "bad_number")
    def work():
        with s.lock:
            kind, city = d.get("kind"), str(d.get("city") or "").strip()[:80]
            needs = d.get("needs") if isinstance(d.get("needs"), list) else []
            if kind not in V.KIND_KEYS or any(n not in V.NEED_KEYS for n in needs): raise HTTPException(400, "bad_choice")
            if not city: raise HTTPException(400, "no_city")
            gst = {"unsure": None, "yes": True, "no": False}.get(d.get("gst"))
            reply = from_form(s.advisor, kind, city, number("tier", 0, 3) or None, number("staff", 1, 100000), number("sites", 1, 10000), gst, needs, bool(d.get("fibre")))
            V.ensure_welcome(s)  # the welcome comes first
            V.add_turn(s, V.say(s)("Filled in the short form", "छोटा फ़ॉर्म भरा"), reply)
            V.track_chat(s)
            return V.advisor(s)
    return await run_in_threadpool(work)


@app.post("/api/advisor/callback")
async def advisor_callback(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            ph, em, err = callback.clean(str(d.get("phone") or ""), str(d.get("email") or ""))
            if not err and d.get("agree") is not True: err = "no_agree"
            if err: return JSONResponse({"problem": V.CALLBACK_ERRORS[err][s.ui_lang == "hi"]}, 400)
            best = d.get("best") if d.get("best") in ("Any time", "Morning", "Afternoon", "Evening") else "Any time"
            callback.save(s.user, str(d.get("name") or "")[:80], ph, em, best, str(d.get("note") or "")[:200], s.advisor.profile.model_dump_json(), s.advisor.handoff or "customer_request", s.ui_lang)
            return V.advisor(s)
    return await run_in_threadpool(work)


@app.delete("/api/advisor/callback")
def advisor_callback_delete(request: Request):
    s = sess(request)
    with s.lock:
        callback.delete(s.user)
        return V.advisor(s)


# ---- Voice: nothing is kept. The words come back to the input box for the owner to check. ------------------------------
@app.post("/api/voice/consent")
def voice_consent(request: Request):
    s = sess(request)
    with s.lock:
        if consent.VOICE not in consent.active(s.user): consent.grant(s.user, consent.VOICE, s.ui_lang)
    return {"ok": True}


@app.post("/api/voice")
async def voice(request: Request):
    s = sess(request)
    try:
        data = await read_limited(request, asr.MAX_BYTES)
    except HTTPException:
        return JSONResponse({"problem": "too_long"}, 413)
    def work():  # off the event loop: the session lock can be held by a chat reply that's waiting on Gemini
        with s.lock:
            if consent.VOICE not in consent.active(s.user): return JSONResponse({"problem": "no_consent"}, 403)
            now = time.time()
            s.voice_times = [t for t in s.voice_times if now - t < 60]
            if len(s.voice_times) >= VOICE_PER_MINUTE: return JSONResponse({"problem": "busy"}, 429)
            s.voice_times.append(now)
            no_ai = bool(s.advisor.no_ai)
        return asr.transcribe(data, no_ai)
    return await run_in_threadpool(work)


# ---- Quote ---------------------------------------------------------------------------------------------------------
def _has_plan(s: Session) -> None:
    if not (s.advisor.rec and s.advisor.rec.quote): raise HTTPException(409, "no_plan")


@app.post("/api/quote/change")
async def quote_change(request: Request):
    """Choices only. No price or total is read from the browser."""
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            _has_plan(s)
            V._quote_state(s)  # applies a reset if the plan has changed
            cat = catalogue()
            pid = d.get("product")
            if d.get("action") == "addon" and pid in V.ADDONS:
                s.addons = (s.addons | {pid}) if d.get("on") else (s.addons - {pid})
            elif d.get("action") == "qty" and pid in cat and cat[pid].unit in ADJUSTABLE_UNITS:
                try: s.qty[pid] = max(1, min(MAX_QTY, int(d.get("value"))))
                except (TypeError, ValueError): raise HTTPException(400, "bad_number")
            elif d.get("action") == "remove" and pid in cat:
                if pid not in s.removed: s.removed.append(pid)
            elif d.get("action") == "restore": s.removed = []
            elif d.get("action") == "alt": s.use_alt = bool(d.get("on"))
            elif d.get("action") == "gstin": s.gstin_tick = bool(d.get("on"))
            else: raise HTTPException(400, "bad_action")
            return V.quote(s)
    return await run_in_threadpool(work)


@app.post("/api/quote/accept")
def quote_accept(request: Request):
    s = sess(request)
    with s.lock:
        _has_plan(s)
        V.accept_quote(s)
        return V.quote(s)


@app.post("/api/quote/compare")
async def quote_compare(request: Request):
    s, d = sess(request), await body(request)  # the bill is used for this one answer and never stored
    def work():
        with s.lock:
            _has_plan(s)
            try: now = int(d.get("now") or 0)
            except (TypeError, ValueError): raise HTTPException(400, "bad_number")
            return V.compare_bill(s, max(0, min(now, 10_000_000))) if now > 0 else {"text": None}
    return await run_in_threadpool(work)


@app.get("/api/quote/download")
def quote_download(request: Request):
    s = sess(request)
    with s.lock:
        _has_plan(s)
        st = V._quote_state(s)
        text = summary_text(st["q"], {p: catalogue()[p].description for p in st["res"]["items"]})
    return PlainTextResponse(text, headers={"Content-Disposition": 'attachment; filename="accel_business_quote.txt"'})


# ---- Consent -------------------------------------------------------------------------------------------------------
@app.post("/api/consent")
async def consent_save(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            active = consent.active(s.user)
            a, b = d.get("kyc") is True and consent.KYC not in active, d.get("updates") is True and consent.UPDATES not in active
            if not (consent.KYC in active or a) or not (a or b): raise HTTPException(400, "kyc_required")
            if a: consent.grant(s.user, consent.KYC, s.ui_lang); V.event(s, "consent_given")
            if b: consent.grant(s.user, consent.UPDATES, s.ui_lang)
            return V.consent_page(s)
    return await run_in_threadpool(work)


@app.post("/api/contact")
async def contact_save(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            if d.get("agree") is not True and consent.CONTACT not in consent.active(s.user):
                return JSONResponse({"problem": V.CONTACT_PROBLEM["no_agree"][s.ui_lang == "hi"]}, 400)
            problem = contacts.save(s.user, str(d.get("name") or ""), str(d.get("phone") or ""), s.ui_lang)
            if problem: return JSONResponse({"problem": V.CONTACT_PROBLEM[problem][s.ui_lang == "hi"]}, 400)
            return V.consent_page(s)
    return await run_in_threadpool(work)


@app.post("/api/consent/withdraw")
async def consent_withdraw(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            if d.get("purpose") not in consent.active(s.user): raise HTTPException(400, "not_active")
            consent.withdraw(s.user, d["purpose"])
            if d["purpose"] == consent.KYC:  # deleted, so none of it may stay in the session
                s.kyc_result, s.typed_gstin, s.lookup, s.pending = None, None, {}, []
        return {"ok": True}
    return await run_in_threadpool(work)


@app.get("/api/consent/receipt")
def consent_receipt(request: Request):
    s = sess(request)
    # A BOM so Hindi opens correctly in basic text viewers.
    return Response(consent.receipt_text(s.user, s.ui_lang).encode("utf-8-sig"), media_type="text/plain; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="accel_business_consent_receipt.txt"'})


# ---- KYC -----------------------------------------------------------------------------------------------------------
def _kyc_allowed(s: Session) -> None:
    if consent.KYC not in consent.active(s.user): raise HTTPException(403, "no_consent")


@app.post("/api/kyc/lookup")
async def kyc_lookup(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            _kyc_allowed(s)
            found, g, u = {}, str(d.get("gstin") or "").strip()[:20], str(d.get("udyam") or "").strip()[:25]
            if g:
                found["gst"] = KP.look_up_gstin(g)
                if found["gst"]["state"] != "bad_format": s.typed_gstin = g  # compared with the certificate, then dropped; never stored
            if u: found["udyam"] = KP.look_up_udyam(u)
            s.lookup = found
            return V.kyc(s)
    return await run_in_threadpool(work)


class _Upload(io.BytesIO):
    @property
    def size(self) -> int: return self.getbuffer().nbytes


def _as_png(img: Image.Image) -> bytes:
    out = io.BytesIO(); img.save(out, "PNG")
    return out.getvalue()


class LazyPages:
    """Pages decoded one at a time, because several phone photos decoded together wouldn't fit on a small server."""
    def __init__(self, blobs: list[bytes]): self.blobs = blobs
    def __len__(self): return len(self.blobs)
    def __iter__(self):
        for b in self.blobs: yield KP.open_image(b)


@app.post("/api/kyc/upload")
async def kyc_upload(request: Request):
    s = sess(request)
    _kyc_allowed(s)
    name = unquote(request.headers.get("x-file-name") or "file")[:80]
    limit = MAX_UPLOAD_MB * 1024 * 1024
    try:
        data = await read_limited(request, limit)
    except HTTPException:
        return JSONResponse({"problem": V.upload_problem(s, "too_big", name)}, 413)
    def work():
        with _decode_slot:
            pages, why = KP.open_upload(_Upload(data))  # the type comes from the content, never the name
        if why: return JSONResponse({"problem": V.upload_problem(s, why, name)}, 400)
        blobs = [_as_png(p) for p in pages] if data[:5] == b"%PDF-" else [data]
        with s.lock:
            if len(s.pending) + len(blobs) > MAX_PAGES: return JSONResponse({"problem": V.upload_problem(s, "too_many", name)}, 400)
            if pending_bytes() + sum(map(len, blobs)) > MAX_PENDING_BYTES: return JSONResponse({"problem": V.upload_problem(s, "busy", name)}, 503)
            s.pending += blobs; s.pending_since = time.time()
            s.pending_signals += forensics.signals(data)
            return {"pending": len(s.pending)}
    return await run_in_threadpool(work)


@app.delete("/api/kyc/upload")
def kyc_upload_clear(request: Request):
    s = sess(request)
    with s.lock: s.pending, s.pending_signals = [], []
    return {"ok": True}


def _run_kyc(s: Session, applicant: str | None, blobs: list[bytes], typed: str | None, gst_optional: bool, signals: list | None = None, no_gstin: bool | None = None) -> None:
    """Runs apart from the request, so a slow read can't hit a proxy's time limit. The page polls for progress."""
    global _waiting
    job = s.kyc_job
    def step(n, total): job.update(done=n, total=total)
    try:
        with _ocr_slot:
            with _waiting_guard: _waiting -= 1
            job["state"], started = "running", time.monotonic()
            if applicant:
                r = KP.verify_images(KP.load_specimen(applicant), progress=lambda k, n, total: step(n, total))
            else:
                r = KP.verify_files(LazyPages(blobs), typed, progress=step, gst_optional=gst_optional, no_gstin_declared=no_gstin if gst_optional else None)
        blobs.clear()
        with s.lock:
            if consent.KYC not in consent.active(s.user):  # withdrawn while it was reading: nothing may be saved
                job["state"] = "done"; return
            if signals: r.fields["signals"] = signals  # for a reviewer only: never part of the verdict
            consent.save_kyc(s.user, r.verdict, r.reason, json.dumps(r.fields))
            V.event(s, "kyc_done", code=r.verdict)
            s.lookup = {}  # an old "go ahead" must not sit above a different verdict
            s.kyc_result = {"verdict": r.verdict, "source": applicant or "upload", "fields": r.fields, "read": r.read, "checks": r.checks, "unused": r.unused, "seconds": round(time.monotonic() - started, 1), "issues": [(i.severity, i.code, i.params) for i in r.issues]}
            if r.verdict == "verified" and s.order_id and orders.get(s.order_id)["stage"] == "Quote accepted":
                orders.advance(s.order_id, "KYC verified")
            job["state"] = "done"
    except OcrUnavailable:
        job["state"] = "error"  # nothing was read, so this says nothing about the documents
    except Exception:  # never leave the page waiting; the message says nothing was decided
        job["state"] = "error"


@app.post("/api/kyc/verify")
async def kyc_verify(request: Request):
    s, d = sess(request), await body(request)
    def work():
        global _waiting
        with s.lock:
            _kyc_allowed(s)
            if s.kyc_job and s.kyc_job["state"] in ("queued", "running"): return V.kyc(s)
            applicant = d.get("applicant") if d.get("mode") == "specimen" else None
            if d.get("mode") == "specimen" and applicant not in SPECIMEN_REVIEW: raise HTTPException(400, "bad_applicant")
            if not applicant and not s.pending: raise HTTPException(400, "no_files")
            with _waiting_guard:
                if _waiting >= MAX_WAITING: return JSONResponse({"problem": V.say(s)("Many people are verifying right now. Please try again in a minute.", "अभी बहुत लोग सत्यापन कर रहे हैं। कृपया एक मिनट बाद कोशिश करें।")}, 503)
                _waiting += 1
            blobs, typed, signals, s.pending, s.pending_signals = s.pending, s.typed_gstin, s.pending_signals, [], []
            s.typed_gstin = None
            s.kyc_job = {"state": "queued", "done": 0, "total": len(FILES) if applicant else len(blobs)}
            threading.Thread(target=_run_kyc, args=(s, applicant, blobs, None if applicant else typed, not applicant and V.no_gst_needed(s), None if applicant else signals, d.get("no_gstin") is True), daemon=True).start()
            return V.kyc(s)
    return await run_in_threadpool(work)


@app.get("/api/kyc/specimen/{applicant}/{doc}")
def kyc_specimen(applicant: str, doc: str):
    if applicant not in SPECIMEN_REVIEW or doc not in FILES: raise HTTPException(404)
    path = KP.DATA / "kyc_documents" / f"{applicant}_{FILES[doc]}.png"
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


# ---- Tracker: every action repeats the checks the buttons were shown under ---------------------------------------------
@app.post("/api/tracker/select")
async def tracker_select(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            own_order(s, d.get("order"))
            s.tracker_order = d["order"]
            return V.tracker(s)
    return await run_in_threadpool(work)


@app.post("/api/order/pay")
async def order_pay(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            o = own_order(s, d.get("order"))
            if not orders.can_pay(o, V.verdict_of(s)): raise HTTPException(409, "cannot_pay")
            if not contacts.get(s.user): raise HTTPException(409, "no_contact")  # the technician needs a way to reach them
            orders.advance(d["order"], "Payment done"); s.paid_notice = True; V.event(s, "paid")
        return {"ok": True}
    return await run_in_threadpool(work)


@app.post("/api/order/demo")
async def order_demo(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            o, verdict = own_order(s, d.get("order")), V.verdict_of(s)
            action = d.get("action")
            if action == "advance" and orders.can_advance(o, verdict):
                if orders.advance(d["order"]) == "Activated": V.event(s, "activated")
            elif action == "fail" and orders.can_pay(o, verdict): s.pay_failed = True
            elif action == "delay" and verdict == "verified" and 3 <= o["stage_index"] < 5 and not orders.delays(d["order"]): orders.mark_delay(d["order"], "fibre")
            else: raise HTTPException(409, "not_now")
            return V.tracker(s)
    return await run_in_threadpool(work)


@app.post("/api/order/reschedule")
async def order_reschedule(request: Request):
    s, d = sess(request), await body(request)
    def work():
        with s.lock:
            o = own_order(s, d.get("order"))
            if not (3 <= o["stage_index"] < 5 and V.verdict_of(s) == "verified"): raise HTTPException(409, "not_now")
            try: new = date.fromisoformat(str(d.get("date")))
            except ValueError: raise HTTPException(400, "bad_date")
            if new.isoformat() != o["install_date"]:
                try: orders.reschedule(d["order"], new)
                except ValueError: raise HTTPException(400, "bad_date")
            return V.tracker(s)
    return await run_in_threadpool(work)


# ---- Bill snap, receipts and data rights ------------------------------------------------------------------------------
@app.post("/api/quote/bill")
async def quote_bill(request: Request):
    """A photo of the owner's current bill: local OCR reads the amount due, then the photo is dropped. Nothing is stored."""
    s = sess(request)
    try:
        data = await read_limited(request, MAX_UPLOAD_MB * 1024 * 1024)
    except HTTPException:
        return {"amount": None}
    def work():
        _has_plan(s)
        with _decode_slot:
            pages, why = KP.open_upload(_Upload(data))
        if not pages: return {"amount": None}
        with _ocr_slot:
            return {"amount": billscan.read_bill(pages[0])}
    return await run_in_threadpool(work)


@app.get("/api/consent/receipt.json")
def consent_receipt_json(request: Request):
    s = sess(request)
    return Response(json.dumps(consent.receipt_json(s.user, s.ui_lang), ensure_ascii=False, indent=2).encode("utf-8"), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="accel_business_consent_receipt.json"'})


@app.get("/api/data/export")
def data_export(request: Request):
    s = sess(request)
    return Response(json.dumps(rights.export(s.user), ensure_ascii=False, indent=2).encode("utf-8"), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="accel_business_my_data.json"'})


@app.post("/api/data/correction")
async def data_correction(request: Request):
    s, d = sess(request), await body(request)
    def work():
        if rights.request_correction(s.user, str(d.get("detail") or "")): raise HTTPException(400, "empty")
        return {"ok": True}
    return await run_in_threadpool(work)


@app.post("/api/data/erase")
async def data_erase(request: Request):
    s, d = sess(request), await body(request)
    if d.get("sure") is not True: raise HTTPException(400, "not_confirmed")
    sid = request.state.sid
    def work():
        with s.lock:
            rights.erase(s.user)
            reset(sid, s.ui_lang)  # nothing of the old session stays: a new identity from here on
        return {"ok": True}
    return await run_in_threadpool(work)


# ---- Find my order (another day or phone) -------------------------------------------------------------------------
FINDS_PER_MINUTE = 60  # across everyone: new browsers can't be used to guess order numbers quickly
_finds: list = []


@app.post("/api/track/find")
async def track_find(request: Request):
    s, d = sess(request), await body(request)
    def work():
        W = V.say(s)
        now = time.time()
        with s.lock:
            s.find_times = [t for t in s.find_times if now - t < find_order.FIND_WINDOW]
            with _waiting_guard:
                _finds[:] = [t for t in _finds if now - t < 60]
                busy = len(_finds) >= FINDS_PER_MINUTE
                if not busy and len(s.find_times) < find_order.MAX_FINDS: _finds.append(now)
            if busy or len(s.find_times) >= find_order.MAX_FINDS:
                return JSONResponse({"problem": W("Too many tries. Please wait 10 minutes and try again.", "बहुत ज़्यादा कोशिशें हुईं। कृपया 10 मिनट बाद फिर कोशिश करें।")}, 429)
            s.find_times.append(now)
            oid, phone = find_order.order_of(d.get("order")), find_order.phone_of(str(d.get("phone") or ""))
            if not oid or not phone:
                return JSONResponse({"problem": W("Enter the order number and a 10-digit mobile number.", "ऑर्डर नंबर और 10 अंकों का मोबाइल नंबर लिखें।")}, 400)
            who = find_order.owner(oid, phone)
            if not who:
                return JSONResponse({"problem": W("We couldn't find an order with that number and mobile. Check both, or talk to a person.", "इस नंबर और मोबाइल से कोई ऑर्डर नहीं मिला। दोनों जाँचें, या किसी व्यक्ति से बात करें।")}, 404)
            if who == s.user:
                s.tracker_order = oid
                return {"done": True}
            s.find = find_order.new_code(who, oid, now)
            return {"code_sent": True, "demo_code": s.find["code"], "to": "••••••" + phone[-4:]}
    return await run_in_threadpool(work)


@app.post("/api/track/verify")
async def track_verify(request: Request):
    s, d, sid = sess(request), await body(request), request.state.sid
    def work():
        W = V.say(s)
        with s.lock:
            result = find_order.check(s.find, str(d.get("code") or ""))
            if result == "ok":
                pending, lang = s.find, s.ui_lang
            else:
                if result != "wrong": s.find = None
                text = {"expired": W("That code has expired. Ask for a new one.", "यह कोड पुराना हो गया है। नया कोड माँगें।"),
                        "too_many": W("Too many wrong codes. Ask for a new one.", "बहुत ज़्यादा गलत कोड। नया कोड माँगें।"),
                        "wrong": W("That code isn't right. Please check it and try again.", "यह कोड सही नहीं है। जाँचकर फिर से लिखें।")}[result]
                return JSONResponse({"problem": text}, 400)
        # The browser now belongs to the order's owner: a fresh session, so nothing of the previous visitor carries over.
        fresh = reset(sid, lang)
        with fresh.lock:
            fresh.user, fresh.tracker_order = pending["user"], pending["order"]
        db.audit(pending["user"], "order_reopened")
        return {"done": True}
    return await run_in_threadpool(work)


# ---- Partner queue -------------------------------------------------------------------------------------------------
@app.post("/api/staff/login")
async def staff_login(request: Request):
    s, d = sess(request), await body(request)
    code = staff_code()
    if not code: return {"ok": True}
    now = time.time()
    with _staff_guard:
        _staff_fails[:] = [t for t in _staff_fails if now - t < 60]
        if len(_staff_fails) >= STAFF_TRIES_PER_MINUTE: return JSONResponse({"problem": "Too many wrong tries. Please wait a minute."}, 429)
        if not hmac.compare_digest(str(d.get("code") or "").strip().encode(), code.encode()):
            _staff_fails.append(now)
            return JSONResponse({"problem": "That passcode isn't right."}, 401)
    with s.lock: s.staff = True
    return {"ok": True}


@app.post("/api/partner/review/propose")
async def review_propose(request: Request):
    d = await body(request)
    def work():
        try: case = int(d.get("case"))
        except (TypeError, ValueError): raise HTTPException(400, "bad_case")
        problem = reviews.propose(case, str(d.get("decision") or ""), str(d.get("note") or ""), str(d.get("maker") or ""))
        if problem: return JSONResponse({"problem": reviews.PROBLEM[problem]}, 400)
        return {"ok": True}
    return await run_in_threadpool(work)


@app.post("/api/partner/review/confirm")
async def review_confirm(request: Request):
    d = await body(request)
    def work():
        if not isinstance(d.get("id"), int): raise HTTPException(400, "bad_id")
        problem = reviews.confirm(d["id"], str(d.get("checker") or ""), d.get("accept") is True)
        if problem: return JSONResponse({"problem": reviews.PROBLEM[problem]}, 400)
        return {"ok": True}
    return await run_in_threadpool(work)


@app.get("/api/partner/whatif")
def partner_whatif(segment: str = "", share: float = 0, price: float = 0, churn: float = 0):
    clamp = lambda v, lo, hi: max(lo, min(hi, v))
    return V.what_if(segment, clamp(share, 0, 1), clamp(price, -0.2, 0.2), clamp(churn, -0.15, 0.1))
def lead_scores() -> dict:
    global _scores
    if _scores is None:
        if SCORES.exists(): _scores = json.loads(SCORES.read_text())
        else:
            from web.build_scores import build  # local runs only; the image ships the scores file
            _scores = build()
    return _scores


_scores = None


def selfcheck_view() -> dict:
    rows = _selfcheck["rows"]
    same = sum(r[1] == "✓" for r in rows)
    return {"state": _selfcheck["state"], "done": _selfcheck["done"], "total": len(SPECIMEN_REVIEW), "headers": ["Applicant", "Same as review", "Result", "Expected", "Why"], "rows": rows, "summary": f"{same} of {len(rows)} match our review." if rows and _selfcheck["state"] == "done" else None, "ok": same == len(rows)}


def _run_selfcheck() -> None:
    rows = []
    try:
        for n, (k, (want, code)) in enumerate(SPECIMEN_REVIEW.items()):
            _selfcheck["done"] = n
            with _ocr_slot: res = KP.verify_specimen(k)
            rows.append([k, "✓" if res.verdict == want and (code is None or code in [x.code for x in res.issues]) else "✗", res.verdict, want, res.reason])
            _selfcheck["rows"] = list(rows)
        _selfcheck["state"] = "done"
    except Exception:
        _selfcheck["state"] = "error"


def evidence_view() -> dict:
    rows = _evidence["rows"]
    ready = all((ROOT / args[-1]).exists() for _, args in EVIDENCE)
    return {"state": _evidence["state"] if ready else "unavailable", "done": _evidence["done"], "total": len(EVIDENCE), "rows": rows, "labels": [label for label, _ in EVIDENCE],
            "all_passed": bool(rows) and _evidence["state"] == "done" and all(r["ok"] for r in rows)}


def _run_one(args: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "LLM_API_KEY": "", "PARTNER_PASSCODE": "", "UDYAM_DB": os.path.join(tmp, "evidence.db"), "PYTHONIOENCODING": "utf-8"}
        try:
            r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=EVIDENCE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"result": "Timed out", "failed": [], "ok": False}
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    total = next((l for l in reversed(lines) if re.match(r"^\d+/\d+ ", l)), None)
    failed = [re.sub(r"^FAIL\s+", "", l)[:120] for l in lines if l.startswith("FAIL")]
    m = re.match(r"^(\d+)/(\d+)", total or "")
    ok = bool(m) and m.group(1) == m.group(2) and r.returncode == 0 and not failed
    return {"result": total or "No result", "failed": failed[:10], "ok": ok}


def _run_evidence() -> None:
    rows = []
    try:
        for n, (label, args) in enumerate(EVIDENCE):
            _evidence["done"] = n
            rows.append({"label": label, "command": "python " + " ".join(args), **_run_one(args)})
            _evidence["rows"] = list(rows)
        _evidence["state"] = "done"
    except Exception:
        _evidence["state"] = "error"


@app.post("/api/partner/evidence")
def partner_evidence():
    if evidence_view()["state"] == "unavailable": raise HTTPException(409, "tests_missing")
    if _evidence["state"] != "running":
        _evidence.update(state="running", done=0, rows=[])
        threading.Thread(target=_run_evidence, daemon=True).start()
    return evidence_view()


@app.post("/api/partner/selfcheck")
def partner_selfcheck():
    if _selfcheck["state"] != "running":
        _selfcheck.update(state="running", done=0, rows=[])
        threading.Thread(target=_run_selfcheck, daemon=True).start()
    return selfcheck_view()


# ---- The page ------------------------------------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, exc.status_code)


@app.get("/sw.js")
def service_worker():
    """Served from the root so it may cover every page; it caches nothing (see the file)."""
    return FileResponse(STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
def page(path: str):
    if "/" + path not in PAGES: raise HTTPException(404, "not_found")
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
