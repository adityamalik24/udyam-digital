"""Shared Streamlit helpers. Pages hold UI only; decisions live in core/."""
import os, sys
from uuid import uuid4
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import streamlit as st
from core.advisor import State
from core.labels import L, T  # noqa: F401 (pages read c.T)



def setup(title: str):
    st.set_page_config(page_title=f"{title} · Accel Business", page_icon="📶", layout="centered")
    st.markdown("<style>.block-container{padding:3.75rem 1rem 4rem;max-width:720px}.big-price{font-size:2.6rem;font-weight:700;line-height:1.1}"
                ".steps{display:flex;list-style:none;margin:0 0 .4rem;padding:0;gap:2px}.steps li{flex:1 1 0;min-width:0;margin:0;padding:0;text-align:center;font-size:.72rem;line-height:1.2}"
                ".steps .dot{display:block;width:1.5rem;height:1.5rem;line-height:calc(1.5rem - 2px);margin:0 auto .15rem;border-radius:50%;border:1px solid currentColor;box-sizing:border-box;font-weight:700}"
                ".steps .done .dot{background:#15803d;border-color:#15803d;color:#fff}.steps .attention .dot{background:#b45309;border-color:#b45309;color:#fff}"
                ".steps .now{font-weight:700}.steps .now .dot{outline:2px solid currentColor;outline-offset:1px}"
                ".steps .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}</style>", unsafe_allow_html=True)
    st.session_state.setdefault("advisor", State())
    # A chat that began before a deploy can miss newer fields: start it fresh instead of crashing.
    if any(not hasattr(st.session_state.advisor, f) for f in State.__dataclass_fields__):
        st.session_state.advisor, st.session_state.chat = State(), []
    from core import orders, retention
    retention.run_once()
    if st.session_state.get("order_id") and not orders.get(st.session_state.order_id):  # the database restarted under this session
        for k in ("order_id", "accepted_items"): st.session_state.pop(k, None)
    st.session_state.setdefault("ui_lang", "en")
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("synced_lang", "en")
    # Follow the language of the chat on every page; the sidebar can still override it afterwards.
    chat_lang = st.session_state.advisor.profile.language
    if chat_lang in L and chat_lang != st.session_state.synced_lang:
        st.session_state.synced_lang = st.session_state.ui_lang = chat_lang
    # Streamlit wipes a widget's value on every page change, so the language lives outside the widget.
    st.session_state.lang_picker = st.session_state.ui_lang
    st.sidebar.radio("Language / भाषा", ["en", "hi"], key="lang_picker", format_func=lambda x: {"en": "English", "hi": "हिन्दी"}[x], on_change=lambda: st.session_state.update(ui_lang=st.session_state.lang_picker))
    st.sidebar.caption("Demo. All data is synthetic. Accel Telecom is fictional.")
    return L[st.session_state.ui_lang]


def user() -> str:
    """One demo identity per browser session, so judges testing at once never see each other's orders or consent."""
    return st.session_state.setdefault("user", f"demo-{uuid4().hex[:8]}")


def event(kind: str, code: str | None = None, variant: str | None = None) -> None:
    """A funnel step for the live dashboard, under a random id that isn't the user id. Never breaks a page."""
    from core import events
    try:
        events.log(st.session_state.setdefault("fid", uuid4().hex), kind, variant=variant, code=code)
    except Exception:
        pass


def variant() -> str:
    """The quote layout this browser sees, fixed for the session."""
    from core import events
    return st.session_state.setdefault("ab_variant", events.variant())


SPEECH_LANG = [("\u0900", "\u097f", "hi-IN"), ("\u0b80", "\u0bff", "ta-IN"), ("\u0c00", "\u0c7f", "te-IN"), ("\u0c80", "\u0cff", "kn-IN"), ("\u0d00", "\u0d7f", "ml-IN"), ("\u0980", "\u09ff", "bn-IN"), ("\u0a80", "\u0aff", "gu-IN"), ("\u0a00", "\u0a7f", "pa-IN")]


def read_aloud(text: str, label: str) -> None:
    """A button that reads a reply aloud with the phone's own voices. Nothing is sent anywhere."""
    import json, re
    import streamlit.components.v1 as components
    plain = re.sub(r"[*_#`>]|\[|\]", "", text).replace("\n- ", ". ").replace("\n", ". ")
    lang = next((code for lo, hi, code in SPEECH_LANG if any(lo <= ch <= hi for ch in plain)), "en-IN")
    components.html(f"""<button id="b" style="font:15px sans-serif;padding:6px 12px;border:1px solid #8c8c8c;border-radius:8px;background:#fff;cursor:pointer">🔊 {label}</button>
<script>const t={json.dumps(plain)},l={json.dumps(lang)},b=document.getElementById("b");
if(!("speechSynthesis" in window)) b.style.display="none";
b.onclick=()=>{{const s=window.speechSynthesis;if(s.speaking){{s.cancel();return;}}const u=new SpeechSynthesisUtterance(t);u.lang=l;const v=s.getVoices().find(x=>x.lang===l)||s.getVoices().find(x=>x.lang.startsWith(l.slice(0,2)));if(v)u.voice=v;s.speak(u);}};</script>""", height=44)


def journey(page: str, t: dict) -> None:
    """Quote to tracking progress, from stored records. Text as well as colour, so it reads without seeing colour."""
    from core import consent, journey as j, orders
    oid = st.session_state.get("order_id") or orders.latest(user())
    last = consent.latest_kyc(user())
    state = j.progress(orders.get(oid) if oid else None, consent.KYC in consent.active(user()), last["verdict"] if last else None)
    now = j.current(page, state)
    items = []
    for i, step in enumerate(j.STEPS, 1):
        mark = {j.DONE: "✓", j.ATTENTION: "!"}.get(state[step], str(i))
        cls, aria = state[step] + (" now" if step == now else ""), ' aria-current="step"' if step == now else ""
        items.append(f'<li class="{cls}"{aria}><span class="dot" aria-hidden="true">{mark}</span>{t["steps"][step]}<span class="vh"> ({t["step_state"][state[step]]})</span></li>')
    st.markdown(f'<ol class="steps">{"".join(items)}</ol>', unsafe_allow_html=True)


def consent_panel(t: dict) -> None:
    """Consent history and withdrawal, in plain words. Reachable with or without an order."""
    from core import consent
    lang = st.session_state.ui_lang
    label = lambda p: consent.PURPOSE_LABEL.get(p, {}).get(lang, p)
    for r in consent.records(user()):
        st.caption(f"{label(r['purpose'])} · {r['notice_version']} · {t['granted']} {r['granted_at'][:16].replace('T', ' ')} UTC" + (f" · {t['withdrawn']} {r['withdrawn_at'][:16].replace('T', ' ')} UTC" if r["withdrawn_at"] else ""))
    held = consent.what_we_hold(user())
    say = (lambda en, h: h if lang == "hi" else en)
    lines = [say(f"Consent records: {held['consents']}", f"सहमति रिकॉर्ड: {held['consents']}"), say(f"Orders: {held['orders']}", f"ऑर्डर: {held['orders']}")]
    if held["kyc"]: lines.append(say(f"KYC result: {t['verdicts'][held['kyc']]}", f"KYC परिणाम: {t['verdicts'][held['kyc']]}"))
    if held["gstin"]: lines.append(f"GSTIN: {held['gstin']}")
    if held["id"]: lines.append(f"ID: {held['id']}")
    if held["callback"]: lines.append(say("Your call-back details", "आपकी कॉल-बैक जानकारी"))
    st.markdown(say("**What we hold about you**  \n", "**आपके बारे में हमारे पास क्या है**  \n") + "  \n".join(lines) + say("  \nNo document images are kept.", "  \nदस्तावेज़ों की तस्वीरें नहीं रखी जातीं।"))
    if consent.records(user()):  # a BOM so Hindi opens correctly in basic text viewers
        st.download_button(t["receipt"], consent.receipt_text(user(), lang).encode("utf-8-sig"), "accel_business_consent_receipt.txt", "text/plain", key="consent_receipt")
        import json as _json
        st.download_button(say("Consent receipt for software (JSON)", "सॉफ़्टवेयर के लिए सहमति रसीद (JSON)"), _json.dumps(consent.receipt_json(user(), lang), ensure_ascii=False, indent=2).encode("utf-8"), "accel_business_consent_receipt.json", "application/json", key="consent_receipt_json")
    link("pages/7_Your_Data.py", label=say("Download, correct or delete your data", "अपना डेटा डाउनलोड करें, ठीक करवाएँ या मिटाएँ"), icon="🗂️")
    for p in sorted(consent.active(user())):
        if p in consent.WITHDRAW_EFFECT: st.caption(consent.WITHDRAW_EFFECT[p][lang])
        if st.button(f"{t['withdraw']}: {label(p)}", key=f"w_{p}"):
            consent.withdraw(user(), p)
            if p == consent.KYC:  # deleted, so none of it may stay on screen or in the session
                for k in ("kyc_result", "lookup", "typed_gstin"): st.session_state.pop(k, None)
            st.rerun()


def link(page: str, **kw):
    """st.page_link, tolerant of running a page as its own entrypoint (headless tests)."""
    from streamlit.errors import StreamlitPageNotFoundError
    try:
        st.page_link(page, **kw)
    except StreamlitPageNotFoundError:
        st.caption(kw.get("label", page))
