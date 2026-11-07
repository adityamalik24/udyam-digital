"""Signs that a file was edited, for a reviewer only. They never change a verdict: an automatic decision still needs
the evidence in checks.py. These are the file-level checks document-fraud tools start with, chosen because a clean
scan or phone photo doesn't trigger them."""
from __future__ import annotations
import io, re
from PIL import Image

EDITORS = re.compile(rb"photoshop|gimp|canva|paint\.net|pixelmator|affinity|illustrator|inkscape|corel|ilovepdf|smallpdf|sejda|pdf-?xchange|foxit\s*phantom|acrobat\s*pro|libreoffice|microsoft\W*word|wps\s*office", re.I)
SIGNAL_TEXT = {"editor_software": "The file was saved by editing software ({tool}).", "pdf_resaved": "The PDF was changed after it was first saved ({n} saves).",
               "pdf_dates_differ": "The PDF's modified date differs from its creation date."}


def signals(data: bytes) -> list[dict]:
    out = []
    if data[:5] == b"%PDF-":
        saves = data.count(b"%%EOF")
        if saves > 1 and b"/ByteRange" not in data: out.append({"code": "pdf_resaved", "n": saves})  # signing a PDF adds a save, so a signed one is expected to have several
        # A re-saved PDF appends a newer information block, so the last one found is the current one.
        created, modified = re.findall(rb"/CreationDate\s*\(D:(\d{8,14})", data), re.findall(rb"/ModDate\s*\(D:(\d{8,14})", data)
        if created and modified and created[-1][:12] != modified[-1][:12]: out.append({"code": "pdf_dates_differ"})
        tool = next((t for t in re.findall(rb"/(?:Producer|Creator)\s*\(([^)]{1,80})\)", data) if EDITORS.search(t)), None)
        if tool: out.append({"code": "editor_software", "tool": tool.decode("latin-1").strip()})
        return out
    try:
        img = Image.open(io.BytesIO(data))
        meta = [str(v) for v in img.info.values() if isinstance(v, (str, bytes))]
        exif = img.getexif()
        meta += [str(exif.get(t, "")) for t in (0x0131, 0x013B)]  # Software, Artist
        xmp = img.info.get("xmp") or b""
        meta.append(xmp.decode("utf-8", "ignore") if isinstance(xmp, bytes) else str(xmp))
    except Exception:
        return out
    blob = " ".join(meta).encode("utf-8", "ignore")
    m = EDITORS.search(blob)
    if m: out.append({"code": "editor_software", "tool": m.group(0).decode("utf-8", "ignore")})
    return out


def describe(sig: dict) -> str:
    return SIGNAL_TEXT[sig["code"]].format(**sig)
