"""Applicant documents to verdict. Images stay in memory, are never persisted, never go to an LLM."""
import io
import struct
import subprocess
import sys
from pathlib import Path
from PIL import Image
from ..catalogue import DATA
from .checks import check_applicant, Result
from .ocr import OcrUnavailable, extract, parse  # noqa: F401 (pages catch OcrUnavailable from here)
from .validators import gstin_problem, mask, valid_udyam
from . import ocr, registry
from . import messages as M

FILES = {"gst": "gst_certificate", "udyam": "udyam_certificate", "id": "signatory_id", "bill": "address_proof"}


# Our own manual review of every image against the registries, NOT the judges' key. Also powers the self-check on the Partner queue.
SPECIMEN_REVIEW = {"K01": ("rejected", "gst_inactive"), "K02": ("verified", None), "K03": ("verified", None),
                   "K04": ("needs_review", "blurry_gst"), "K05": ("needs_review", "missing_udyam"),
                   "K06": ("rejected", "gst_number_mismatch"), "K07": ("needs_review", "legal_name_mismatch"),
                   "K08": ("verified", None), "K09": ("verified", None), "K10": ("needs_review", "signatory_vs_lead"),
                   "K11": ("needs_review", "bill_stale"), "K12": ("verified", None)}


def verify_images(images: dict, entered_gstin: str | None = None, progress=None) -> Result:
    """progress, if given, is called with (document key, documents done, total) as each one is read."""
    out = {}
    for n, (k, img) in enumerate(images.items()):
        if progress: progress(k, n, len(images))
        out[k] = extract(img, k)
    return check_applicant(out, entered_gstin)


def load_specimen(applicant: str) -> dict:
    out = {}
    for key, name in FILES.items():
        p = DATA / "kyc_documents" / f"{applicant}_{name}.png"
        if p.exists():
            out[key] = Image.open(p)
    return out


MAX_UPLOAD_MB, MAX_PIXELS = 10, 40_000_000  # bigger than any phone photo; a larger file is refused before it is decoded
MAX_PIXELS_FULL = 25_000_000  # a PNG can't be decoded at a reduced size, so a larger one wouldn't fit in a small server's memory
MAX_PAGES = 8      # across everything sent at once: 4 documents, with room for a repeat or a back page
PDF_SECONDS = 25   # a file that takes longer than this to draw is refused
PDF_DPI = 200      # higher made small print worse in testing: pages are upscaled past what they hold


def _pdf_pages(data: bytes) -> list[Image.Image]:
    """Each page drawn in its own process with a time limit, then read with OCR like any photo.
    A PDF's text layer is never trusted: it can differ from what's shown."""
    try:
        done = subprocess.run([sys.executable, str(Path(__file__).with_name("pdf_worker.py")), str(PDF_DPI), str(MAX_PAGES)], input=data, capture_output=True, timeout=PDF_SECONDS)
    except subprocess.TimeoutExpired as e:
        raise ValueError("PDF took too long") from e
    if done.returncode == 3: raise OverflowError
    if done.returncode != 0: raise ValueError("PDF could not be drawn")
    pages, out, at = [], done.stdout, 0
    while at < len(out):
        size = struct.unpack(">I", out[at:at + 4])[0]; at += 4
        pages.append(Image.open(io.BytesIO(out[at:at + size])).copy()); at += size
    if not pages: raise ValueError("PDF has no pages")
    return pages


def open_image(data: bytes) -> Image.Image:
    """Open a photo without holding it whole in memory when it's huge. A big JPEG is decoded at a half, quarter or eighth
    of its size, never smaller than OCR uses (it is scaled to that size anyway). Raises OverflowError("too_big")."""
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_PIXELS: raise OverflowError("too_big")
    if img.format == "JPEG": img.draft(None, (ocr.MAX_SIDE, ocr.MAX_SIDE))
    elif img.width * img.height > MAX_PIXELS_FULL: raise OverflowError("too_big")
    return img


def open_upload(file) -> tuple[list[Image.Image], str | None]:
    """Open an uploaded image or PDF in memory. Returns (pages, None), or ([], why): too_big, too_many, or bad_file for anything
    unreadable, damaged or password-protected. The type comes from the content, never the file name."""
    if getattr(file, "size", 0) > MAX_UPLOAD_MB * 1024 * 1024: return [], "too_big"
    try:
        data = file.read()
        if data[:5] == b"%PDF-": return _pdf_pages(data), None
        return [open_image(data).copy()], None
    except OverflowError as e:
        return [], "too_big" if str(e) == "too_big" else "too_many"
    except (OSError, ValueError, SyntaxError, struct.error, Image.DecompressionBombError):
        return [], "bad_file"


def sort_documents(images: list, progress=None) -> tuple[dict, tuple, int]:
    """Work out which document each file is. Returns (documents, types with two different documents, files not recognised).
    One unrecognised file with one type missing is taken to be that type, which is how a blurred page still gets the right
    message. Beyond that we don't guess: anything still missing goes to a person."""
    docs, duplicates, unknown = {}, [], []
    for n, img in enumerate(images):
        if progress: progress(n, len(images))
        ex = extract(img)
        if ex.doc is None: unknown.append(ex)
        elif ex.doc not in docs: docs[ex.doc] = ex
        elif _content(ex) != _content(docs[ex.doc]) and ex.doc not in duplicates: duplicates.append(ex.doc)
    gaps = [k for k in FILES if k not in docs]
    if len(unknown) == 1 and len(gaps) == 1:
        ex = unknown.pop(); ex.doc = gaps[0]; ex.fields = parse(ex.text, ex.doc); docs[ex.doc] = ex
    return docs, tuple(duplicates), len(unknown)


def _content(ex) -> dict:
    return {k: v for k, v in ex.fields.items() if k != "gstin_reads"}


def verify_files(images: list, entered_gstin: str | None = None, progress=None, gst_optional: bool = False) -> Result:
    """Files in any order, of any type mix: sort them, then run the same checks as everything else."""
    docs, duplicates, unused = sort_documents(images, progress)
    r = check_applicant(docs, entered_gstin, duplicates=duplicates, gst_optional=gst_optional)
    r.unused = unused
    return r


def look_up_gstin(typed: str) -> dict:
    """Instant registry check before any upload. Only the status comes back, never a name or address, so it can't be used to
    look up other people's businesses. The number is compared as typed and never corrected."""
    g = "".join((typed or "").upper().split())
    if gstin_problem(g): return {"state": "bad_format"}
    rec, exact = registry.lookup_gstin(g)
    if not (rec and exact): return {"state": "not_found"}
    return {"state": rec["status"].lower(), "masked": mask(g)}


def look_up_udyam(typed: str) -> dict:
    u = "".join((typed or "").upper().split())
    if not valid_udyam(u): return {"state": "bad_format"}
    return {"state": "found", "masked": mask(u)} if registry.lookup_udyam(u) else {"state": "not_found"}


def verify_specimen(applicant: str) -> Result:
    return verify_images(load_specimen(applicant))
