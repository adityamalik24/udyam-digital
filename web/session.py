"""One demo identity per browser, held on the server. A price or verdict never comes from the browser: it only sends choices."""
from __future__ import annotations
import os, random, secrets, threading, time
from dataclasses import dataclass, field
from uuid import uuid4
from core.advisor import State

COOKIE = "udyam_sid"
IDLE_SECONDS = 6 * 3600
UPLOAD_SECONDS = 15 * 60       # uploads nobody verified are dropped after this
MAX_SESSIONS = 1000
MAX_PENDING_BYTES = 120 * 1024 * 1024  # across everyone, because uploads wait in memory on a small server


def pick_variant() -> str:
    """Quote layout for the A/B test. AB_TEST=off shows everyone layout A, so a demo or a judge sees one screen."""
    return "A" if os.environ.get("AB_TEST", "on").strip().lower() in ("off", "0", "false", "no") else random.choice(("A", "B"))


@dataclass
class Session:
    user: str = field(default_factory=lambda: f"demo-{uuid4().hex[:8]}")
    advisor: State = field(default_factory=State)
    chat: list = field(default_factory=list)  # {"role", "text", "lang"}; the welcome is {"welcome": True} and drawn in the page's language
    tr: dict = field(default_factory=dict)       # (message index, language) -> translated text, or None if it couldn't be done
    translating: bool = False                     # a translation run is in progress (views.translate_chat)
    switched_before: int = 0                      # messages before this index were on screen when the language was switched
    ui_lang: str = "en"
    synced_lang: str = "en"
    # Quote choices. The price is worked out again from these on every request.
    plan_id: tuple | None = None
    use_alt: bool = False
    removed: list = field(default_factory=list)
    addons: set = field(default_factory=set)
    qty: dict = field(default_factory=dict)
    gstin_tick: bool = False
    order_id: int | None = None
    accepted_items: dict | None = None
    # KYC. pending holds files in memory only, until they are verified or expire.
    lookup: dict = field(default_factory=dict)
    typed_gstin: str | None = None
    pending: list = field(default_factory=list)
    pending_since: float = 0.0
    kyc_job: dict | None = None
    kyc_result: dict | None = None
    # One-time notices on the tracker.
    paid_notice: bool = False
    pay_failed: bool = False
    tracker_order: int | None = None
    voice_times: list = field(default_factory=list)
    pending_signals: list = field(default_factory=list)  # file-edit signs found at upload, for a reviewer only
    fid: str = field(default_factory=lambda: uuid4().hex)  # funnel id for the dashboard: random, never the user id
    ab: str = field(default_factory=pick_variant)  # quote layout for the A/B test
    staff: bool = False      # entered the staff passcode, when one is set
    find: dict | None = None  # a one-time code waiting to reopen an order (core.find_order)
    find_times: list = field(default_factory=list)
    seen: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock)


_sessions: dict[str, Session] = {}
_guard = threading.Lock()


def _sweep(now: float) -> None:
    for sid, s in list(_sessions.items()):
        if now - s.seen > IDLE_SECONDS: del _sessions[sid]
        elif s.pending and now - s.pending_since > UPLOAD_SECONDS: s.pending = []
    while len(_sessions) >= MAX_SESSIONS:
        del _sessions[min(_sessions, key=lambda k: _sessions[k].seen)]


def get_or_create(sid: str | None) -> tuple[str, Session, bool]:
    now = time.time()
    with _guard:
        _sweep(now)
        if sid and sid in _sessions:
            _sessions[sid].seen = now
            return sid, _sessions[sid], False
        sid = secrets.token_urlsafe(24)  # a browser's old id isn't reused, so it can't choose its own
        _sessions[sid] = Session()
        return sid, _sessions[sid], True


def reset(sid: str, ui_lang: str) -> Session:
    """A fresh identity after erasure: nothing of the old session stays."""
    with _guard:
        fresh = Session(ui_lang=ui_lang, synced_lang=ui_lang)
        fresh.advisor.profile.language = ui_lang  # the chat starts in the page's language, or the page would flip back to English
        _sessions[sid] = fresh
        return fresh


def pending_bytes() -> int:
    with _guard:
        return sum(len(b) for s in _sessions.values() for b in s.pending)
