"""Applicant documents to verdict. Images stay in memory, are never persisted, never go to an LLM."""
from PIL import Image
from ..catalogue import DATA
from .checks import check_applicant, Result
from .ocr import extract

FILES = {"gst": "gst_certificate", "udyam": "udyam_certificate", "id": "signatory_id", "bill": "address_proof"}


def verify_images(images: dict, entered_gstin: str | None = None) -> Result:
    return check_applicant({k: extract(img, k) for k, img in images.items()}, entered_gstin)


def load_specimen(applicant: str) -> dict:
    out = {}
    for key, name in FILES.items():
        p = DATA / "kyc_documents" / f"{applicant}_{name}.png"
        if p.exists():
            out[key] = Image.open(p)
    return out


def verify_specimen(applicant: str) -> Result:
    return verify_images(load_specimen(applicant))
