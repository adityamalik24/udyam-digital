"""Applicant documents to verdict. Images stay in memory, are never persisted, never go to an LLM."""
from PIL import Image
from ..catalogue import DATA
from .checks import check_applicant, Result
from .ocr import extract
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


def open_upload(file) -> tuple[Image.Image | None, str | None]:
    """Open an uploaded file in memory. Returns (image, None), or (None, why): too_big, or bad_file for anything that isn't a readable image."""
    if getattr(file, "size", 0) > MAX_UPLOAD_MB * 1024 * 1024: return None, "too_big"
    try:
        img = Image.open(file)
        if img.width * img.height > MAX_PIXELS: return None, "too_big"
        return img.copy(), None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):  # not an image, empty, or cut off
        return None, "bad_file"


def verify_specimen(applicant: str) -> Result:
    return verify_images(load_specimen(applicant))
