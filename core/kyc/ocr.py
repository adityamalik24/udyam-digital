"""Tesseract text extraction and field parsing. Records what is printed, without correcting it."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageFilter
import pytesseract

DOC_LABELS = {
    "gst": {"gstin": r"GSTIN", "legal_name": r"Legal name", "trade_name": r"Trade name", "constitution": r"Constitution",
            "address": r"Address of principal", "address2": r"place of business", "liability_date": r"Date of liability"},
    "udyam": {"udyam": r"Udyam reg\. ?number", "name": r"Enterprise name", "activity": r"Major activity", "city": r"City",
              "state": r"State", "reg_date": r"Date of registration"},
    "bill": {"consumer": r"Consumer no\.?", "billed_to": r"Billed to", "address": r"Supply address", "date": r"Bill date"},
    "id": {"name": r"Name", "designation": r"Designation", "business": r"For business", "id_no": r"ID no\.?", "valid_till": r"Valid till"},
}


@dataclass
class Extracted:
    doc: str
    fields: dict[str, str] = field(default_factory=dict)
    sharpness: float = 0.0
    skew: float = 0.0
    confidence: float = 0.0
    text: str = ""


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


def extract(img: Image.Image, doc: str) -> Extracted:
    ex = Extracted(doc=doc, sharpness=sharpness(img))
    img = img.convert("RGB")
    ink = _ink(img)
    ex.skew = find_skew(ink)
    if abs(ex.skew) >= 1:
        img = img.rotate(ex.skew, expand=True, fillcolor="white", resample=Image.BICUBIC); ink = _ink(img)
    big = ink.resize((ink.width * 2, ink.height * 2), Image.LANCZOS)
    data = pytesseract.image_to_data(big, config="--psm 6", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, t in zip(data["conf"], data["text"]) if t.strip() and float(c) >= 0]
    ex.confidence = sum(confs) / len(confs) if confs else 0.0
    ex.text = pytesseract.image_to_string(big, config="--psm 6")
    ex.fields = parse(ex.text, doc)
    if doc == "gst" and "gstin" in ex.fields:
        chosen, reads = read_gstin_line(ink)
        if chosen:
            ex.fields["gstin"] = chosen
            ex.fields["gstin_reads"] = ",".join(reads)
    return ex


def read_gstin_line(ink: Image.Image) -> tuple[str, list[str]]:
    """Dedicated pass over the monospace GSTIN line. Returns (chosen read, all reads).
    Tries several scales and takes the first that passes the checksum, otherwise the most
    common read. Reads are chosen between, never edited, so a wrong printed digit still fails."""
    from collections import Counter
    from .validators import gstin_problem
    d = pytesseract.image_to_data(ink, config="--psm 6", output_type=pytesseract.Output.DICT)
    idx = next((i for i, t in enumerate(d["text"]) if t.strip().upper().startswith("GSTIN")), None)
    if idx is None:
        return "", []
    y, h, x, w = d["top"][idx], d["height"][idx], d["left"][idx], d["width"][idx]
    crop = ink.crop((x + w + 10, max(y - h, 0), ink.width - 40, y + 2 * h))
    cfg = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    reads = []
    for scale in (2, 3, 4, 5, 6):
        im = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1))
        t = re.sub(r"[^A-Z0-9]", "", pytesseract.image_to_string(im, config=cfg))
        if t: reads.append(t)
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
    if doc == "gst":
        out["address"] = (out.get("address", "") + out.pop("address2", "")).strip()
    for k in ("gstin", "udyam", "id_no"):
        if k in out: out[k] = re.sub(r"\s+", "", out[k])
    return out
