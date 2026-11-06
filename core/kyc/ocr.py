"""Tesseract text extraction and field parsing. Records what is printed, without correcting it."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageFilter, ImageOps
import pytesseract
from rapidfuzz import fuzz

class OcrUnavailable(Exception):
    """Tesseract can't run here. Nothing has been read, so no verdict can be given."""


OCR_TIMEOUT = 20      # seconds per Tesseract call, so a junk upload can't hang the page
MAX_SIDE = 3000       # larger photos are scaled down first; OCR gains nothing above this
RELIABLE_WIDTH = 1000 # below this, or tilted, a persistent misread is too likely to count as evidence of alteration
READABLE_FIELDS = 3
BLUR_FLOOR = 150      # same floor the checks use: a blurred page is not worth turning round
DIM_BELOW, WEAK_INK, GRAINY = 200, 90, 1500  # clean specimens: brightest part 237+, darkest ink under 40, sharpness under 950

DOC_LABELS = {
    "gst": {"gstin": r"GSTIN", "legal_name": r"Legal name", "trade_name": r"Trade name", "constitution": r"Constitution",
            "address": r"Address of principal", "address2": r"place of business", "liability_date": r"Date of liability"},
    "udyam": {"udyam": r"Udyam reg\. ?number", "name": r"Enterprise name", "activity": r"Major activity", "city": r"City",
              "state": r"State", "reg_date": r"Date of registration"},
    "bill": {"consumer": r"Consumer no\.?", "billed_to": r"Billed to", "address": r"Supply address", "date": r"Bill date"},
    "id": {"name": r"Name", "designation": r"Designation", "business": r"For business", "id_no": r"ID no\.?", "valid_till": r"Valid till"},
}


PLAIN_LABELS = {"gst": {"gstin": "GSTIN", "legal_name": "Legal name", "trade_name": "Trade name", "constitution": "Constitution", "address": "Address of principal", "address2": "place of business", "liability_date": "Date of liability"},
                "udyam": {"udyam": "Udyam reg. number", "name": "Enterprise name", "activity": "Major activity", "reg_date": "Date of registration"},
                "bill": {"consumer": "Consumer no.", "billed_to": "Billed to", "address": "Supply address", "date": "Bill date"},
                "id": {"designation": "Designation", "business": "For business", "valid_till": "Valid till"}}
LABEL_MIN = 74  # "Legai narne" reads about 76; "Trade name" against "Legal name" stays under this


@dataclass
class Extracted:
    doc: str
    fields: dict[str, str] = field(default_factory=dict)
    sharpness: float = 0.0
    skew: float = 0.0
    text: str = ""
    looks_like: str | None = None  # the document type this text most resembles
    reliable: bool = False         # good enough for a persistent mismatch to count as hard evidence


def sharpness(img: Image.Image) -> float:
    """Variance of a Laplacian. Clean specimens score far above the blurred one."""
    g = np.asarray(img.convert("L").filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)), float)
    return float(g.var())


def _ink(img: Image.Image) -> Image.Image:
    """Keep dark text and drop the pink diagonal watermark, which has high red."""
    a = np.asarray(img.convert("RGB"), int)
    mask = (a[..., 0] < 150) & (a.max(axis=2) - a.min(axis=2) < 90)
    return Image.fromarray(np.where(mask, 0, 255).astype("uint8"))


def find_skew(ink: Image.Image) -> float:
    small = ink.copy(); small.thumbnail((620, 620))
    best, top = 0.0, -1.0
    for ang in np.arange(-12, 12.01, 0.5):
        prof = (255 - np.asarray(small.rotate(float(ang), fillcolor=255), float)).sum(axis=1)
        s = float(((prof[1:] - prof[:-1]) ** 2).sum())
        if s > top: best, top = float(ang), s
    return best


def prepare(img: Image.Image) -> Image.Image:
    """Undo what phones and editors do to a file: sideways EXIF, transparency, oversize. Content is untouched."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        rgba = img.convert("RGBA"); flat = Image.new("RGB", rgba.size, "white"); flat.paste(rgba, mask=rgba.getchannel("A")); img = flat
    else:
        img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img = img.copy(); img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return img


def clean_up(img: Image.Image, sharp: float) -> Image.Image:
    """Help a poor photo reach OCR: lift dim or uneven light, stretch weak contrast, calm grain, enlarge a small image.
    Each step has a trigger that no clean scan meets (see tests), so good documents are read exactly as they are."""
    a = np.asarray(img.convert("L"), float); h, w = a.shape
    thirds = (a[:, :w // 3], a[:, w // 3:2 * w // 3], a[:, 2 * w // 3:], a[:h // 3], a[h // 3:2 * h // 3], a[2 * h // 3:])
    if sharp > GRAINY: img = img.filter(ImageFilter.MedianFilter(3))
    if min(np.percentile(t, 95) for t in thirds) < DIM_BELOW:
        small = img.resize((max(w // 8, 1), max(h // 8, 1))).filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.BILINEAR)
        img = Image.fromarray(np.clip(np.asarray(img, float) / np.maximum(np.asarray(small, float), 1) * 245, 0, 255).astype("uint8"))
    if np.percentile(np.asarray(img.convert("L"), float), 0.5) > WEAK_INK:
        img = ImageOps.autocontrast(img, cutoff=(0.5, 2))
    if img.width < RELIABLE_WIDTH:
        img = img.resize((1240, round(img.height * 1240 / img.width)), Image.LANCZOS)
    return img


def _text(img: Image.Image, config: str) -> str:
    try:
        return pytesseract.image_to_string(img, config=config, timeout=OCR_TIMEOUT)
    except pytesseract.TesseractNotFoundError as e:
        raise OcrUnavailable from e
    except RuntimeError:  # pytesseract raises this on timeout: treat as nothing read
        return ""


def _looks_like(text: str) -> str | None:
    hits = {d: sum(k != "address2" for k in parse(text, d)) for d in DOC_LABELS}
    best = max(hits, key=hits.get)
    return best if hits[best] >= READABLE_FIELDS else None


def _read(img: Image.Image, doc: str):
    """Straighten a small tilt, then read. Returns (straightened page, ink, text, fields, skew)."""
    ink = _ink(img)
    skew = find_skew(ink)
    if abs(skew) >= 1:
        img = img.rotate(skew, expand=True, fillcolor="white", resample=Image.BICUBIC); ink = _ink(img)
    text = _text(ink.resize((ink.width * 2, ink.height * 2), Image.LANCZOS), "--psm 6")
    return img, ink, text, parse(text, doc) if doc else {}, skew


def extract(img: Image.Image, doc: str | None = None) -> Extracted:
    """Read one document. With doc=None its type is worked out from the text; ex.doc stays None if it can't be told."""
    img = prepare(img)
    ex = Extracted(doc=doc, sharpness=sharpness(img))
    good_size = img.width >= RELIABLE_WIDTH
    img = clean_up(img, ex.sharpness)
    page, ink, ex.text, ex.fields, ex.skew = _read(img, doc)
    ex.looks_like = _looks_like(ex.text)
    if len(ex.fields) < READABLE_FIELDS and ex.looks_like is None and ex.sharpness >= BLUR_FLOOR and ex.text.strip():
        for turn in (90, 270, 180):  # a sideways or upside-down page, as phone photos often are
            turned = img.rotate(turn, expand=True)
            t_page, t_ink, t_text, t_fields, t_skew = _read(turned, doc)
            if len(t_fields) >= READABLE_FIELDS or _looks_like(t_text):
                page, ink, ex.text, ex.fields, ex.skew = t_page, t_ink, t_text, t_fields, t_skew
                ex.looks_like = _looks_like(t_text); img = turned
                break
    if doc is None and ex.looks_like:
        doc = ex.doc = ex.looks_like; ex.fields = parse(ex.text, doc)
    ex.reliable = abs(ex.skew) < 1 and good_size and img.width >= RELIABLE_WIDTH
    if doc == "gst" and "gstin" in ex.fields:
        chosen, reads = read_gstin_line(ink, page, abs(ex.skew) < 1)
        if chosen:
            ex.fields["gstin"] = chosen
            ex.fields["gstin_reads"] = ",".join(reads)
    return ex


def read_gstin_line(ink: Image.Image, page: Image.Image | None = None, straight: bool = True) -> tuple[str, list[str]]:
    """Dedicated passes over the monospace GSTIN line. Returns (chosen read, all reads).
    Enlarging the colour page before removing the background keeps the strokes crisp, so reads of a straight page agree
    far more often. A tilted page has already been resampled and reads better from its own ink, so it gets both.
    Reads are chosen between, never edited, so a wrong printed digit still fails."""
    from collections import Counter
    from .validators import gstin_problem
    try:
        d = pytesseract.image_to_data(ink, config="--psm 6", output_type=pytesseract.Output.DICT, timeout=OCR_TIMEOUT)
    except pytesseract.TesseractNotFoundError as e:
        raise OcrUnavailable from e
    except RuntimeError:
        return "", []
    idx = next((i for i, t in enumerate(d["text"]) if t.strip().upper().startswith("GSTIN")), None)
    if idx is None:
        return "", []
    y, h, x, w = d["top"][idx], d["height"][idx], d["left"][idx], d["width"][idx]
    box = (x + w + 10, max(y - h, 0), ink.width - 40, y + 2 * h)
    cfg = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    reads = []
    def read(im):
        t = re.sub(r"[^A-Z0-9]", "", _text(im.filter(ImageFilter.GaussianBlur(1)), cfg))
        if t: reads.append(t)
    if page is not None:
        crop = page.crop(box); sharp = _ink(crop.resize((crop.width * 3, crop.height * 3), Image.BICUBIC))
        for scale in (1, 1.5, 2, 2.5, 3):
            read(sharp.resize((int(sharp.width * scale), int(sharp.height * scale)), Image.LANCZOS))
    if page is None or not straight:
        crop = ink.crop(box)
        for scale in (2, 3, 4, 5, 6):
            read(crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS))
    for t in reads:
        if gstin_problem(t) is None:
            return t, reads
    return (Counter(reads).most_common(1)[0][0] if reads else ""), reads


def parse(text: str, doc: str) -> dict[str, str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out: dict[str, str] = {}
    labels = DOC_LABELS[doc]
    for i, line in enumerate(lines):
        for key, pat in labels.items():
            m = re.match(rf"{pat}\s*[:|]?\s*(.*)$", line, re.I)
            if m and key not in out:
                val = m.group(1).strip()
                if not val and doc == "id" and i + 1 < len(lines):
                    val = lines[i + 1].strip()  # ID cards print the value under the label
                out[key] = val
                # Bill addresses wrap on to an unlabelled next line
                if doc == "bill" and key == "address" and i + 1 < len(lines) and not re.match("Bill date", lines[i + 1], re.I):
                    out[key] = val + lines[i + 1].strip()
                break
    # A label OCR slightly misread ("Legai narne") is still that label, but only a near match counts.
    for key, label in PLAIN_LABELS[doc].items():
        if key in out: continue
        n = len(label.split())
        for i, line in enumerate(lines):
            words = line.split()
            if len(words) >= n and fuzz.ratio(" ".join(words[:n]).lower(), label.lower()) >= LABEL_MIN:
                val = " ".join(words[n:]).strip()
                if not val and doc == "id" and i + 1 < len(lines): val = lines[i + 1].strip()
                out[key] = val
                break
    if doc == "gst":
        out["address"] = (out.get("address", "") + out.pop("address2", "")).strip()
    for k in ("gstin", "udyam", "id_no"):
        if k in out: out[k] = re.sub(r"\s+", "", out[k])
    return out
