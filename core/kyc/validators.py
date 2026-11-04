"""Format checks. They validate what was printed and never alter it."""
import re

STATE_CODES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}
_A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z][A-Z0-9][0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-00-\d{7}$")


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _A.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _A[(36 - total % 36) % 36]


def gstin_problem(g: str) -> str | None:
    """None when valid. Note: README says the PAN's 4th char is always X, which the pattern accepts."""
    if not g or len(g) != 15: return "must be 15 characters"
    if not GSTIN_RE.match(g): return "does not follow the GSTIN pattern"
    if g[:2] not in STATE_CODES: return "has an invalid state code"
    if gstin_checksum(g[:14]) != g[14]: return "fails the GSTIN checksum"
    return None


def valid_udyam(u: str) -> bool:
    return bool(u and UDYAM_RE.match(u))


def pan_in_gstin(g: str) -> str:
    return g[2:12]


def mask(value: str | None) -> str:
    if not value: return ""
    return "•" * max(len(value) - 4, 0) + value[-4:]
