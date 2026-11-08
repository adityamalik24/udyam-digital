"""Finding an order again, on another day or phone: the order number, the mobile number the owner gave on the
Consent page, then a one-time code. In this demo the code is shown on screen; a real launch sends it by SMS.
Nothing new is collected: the mobile is the one already held under the owner's contact consent."""
from __future__ import annotations
import hmac, re, secrets, time
from . import contacts, orders
from .guardrails import latin_digits
from .callback import digits, mobile

CODE_SECONDS = 300      # a code works for 5 minutes
MAX_CODE_TRIES = 3      # then a new code is needed
MAX_FINDS = 5           # lookups per browser per 10 minutes, so numbers can't be guessed
FIND_WINDOW = 600


def phone_of(text: str) -> str | None:
    return mobile(text)


def order_of(text) -> int | None:
    """"12", "#12", "Order 12" or "१२". Only one number may be in it, so a phone number typed here isn't read as an order."""
    found = re.findall(r"[0-9]+", latin_digits(str(text or "")))
    return int(found[0]) if len(found) == 1 and len(found[0]) <= 9 and int(found[0]) > 0 else None


def owner(order_id: int, phone: str) -> str | None:
    """The order's owner, only if the mobile matches the one they gave and their consent for it is still active."""
    o = orders.get(order_id)
    if not o: return None
    held = contacts.get(o["user"])
    if not held or not hmac.compare_digest(held["phone"], phone): return None
    return o["user"]


def new_code(user: str, order_id: int, now: float | None = None) -> dict:
    return {"user": user, "order": order_id, "code": f"{secrets.randbelow(10 ** 6):06d}", "expires": (now or time.time()) + CODE_SECONDS, "tries": 0}


def check(pending: dict | None, code: str, now: float | None = None) -> str:
    """'ok', 'expired', 'too_many' or 'wrong'. Counts the try."""
    if not pending or (now or time.time()) > pending["expires"]: return "expired"
    if pending["tries"] >= MAX_CODE_TRIES: return "too_many"
    pending["tries"] += 1
    return "ok" if hmac.compare_digest(pending["code"], digits(code)) else ("too_many" if pending["tries"] >= MAX_CODE_TRIES else "wrong")
