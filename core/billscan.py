"""Reads the amount due from a photo of the owner's current bill, so the quote can be compared with it.
Local OCR only, nothing goes to the LLM, and the photo is never kept. The owner always sees and can change what we read."""
from __future__ import annotations
import re
from PIL import Image
from .kyc import ocr

# Amount labels found on Indian telecom and utility bills, strongest first.
LABELS = [r"total\s+amount\s+(?:due|payable)", r"amount\s+(?:due|payable)", r"net\s+(?:amount\s+)?payable", r"total\s+(?:due|payable)", r"bill\s+amount", r"total\s+(?:bill|charges)", r"grand\s+total",
          r"कुल\s+(?:देय|राशि)", r"देय\s+राशि"]
AMOUNT = re.compile(r"(?:₹|rs\.?|inr)?\s*\(?(?:inr|rs\.?)?\)?\s*[:\-]?\s*₹?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d{1,7}(?:\.\d{1,2})?)", re.I)
MAX_AMOUNT = 1_000_000  # a small business's monthly phone and internet bill is far below this


def amount_from_text(text: str) -> int | None:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for label in LABELS:
        rx = re.compile(label, re.I)
        for i, line in enumerate(lines):
            m = rx.search(line)
            if not m: continue
            for chunk in (line[m.end():], lines[i + 1] if i + 1 < len(lines) else ""):  # the figure can sit on the next line
                a = AMOUNT.search(chunk)
                if a:
                    value = round(float(a.group(1).replace(",", "")))
                    if 0 < value < MAX_AMOUNT: return value
    return None


def read_bill(img: Image.Image) -> int | None:
    """The amount due, or None if we can't find one we trust. Never guesses from a random number on the page."""
    page = ocr.clean_up(ocr.prepare(img), 10_000)
    ink = ocr._ink(page)
    for source in (ink.resize((ink.width * 2, ink.height * 2), Image.LANCZOS), page.convert("L")):
        found = amount_from_text(ocr._text(source, "--psm 6"))
        if found: return found
    return None
