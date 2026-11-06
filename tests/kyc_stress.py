"""Slow KYC robustness run, separate from pytest (several minutes): python tests/kyc_stress.py
1. Degrades every applicant's documents the way real uploads get degraded. Clean applicants must never be rejected,
   and applicants with a planted problem must never verify.
2. Makes cut-and-paste forgeries of clean GST certificates, copying one printed GSTIN character over another.
   None may verify, whether straight, dim, tilted or in a PDF."""
import io, os, sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
os.environ["OMP_THREAD_LIMIT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from core.kyc import registry
from core.kyc.ocr import _ink
from core.kyc.pipeline import SPECIMEN_REVIEW, load_specimen, open_upload, verify_images

CLEAN = {k for k, (verdict, _) in SPECIMEN_REVIEW.items() if verdict == "verified"}
STRAIGHT_CLEAN = {"K03": "27XUIXG0767D1ZP", "K08": "24XORXG9365M1Z3", "K09": "37LDYXK0296F1ZB", "K12": "37NBLXS1145E1ZU"}


def jpeg(q):
    def f(im):
        b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=q); b.seek(0); return Image.open(b).copy()
    return f


def scale(s): return lambda im: im.resize((int(im.width * s), int(im.height * s)), Image.BILINEAR)
def turn(a): return lambda im: im.convert("RGB").rotate(a, expand=True, fillcolor="white", resample=Image.BICUBIC)
def bright(v): return lambda im: ImageEnhance.Brightness(im.convert("RGB")).enhance(v)
def blur(r): return lambda im: im.convert("RGB").filter(ImageFilter.GaussianBlur(r))


def grain(sd):
    def f(im):
        a = np.asarray(im.convert("RGB"), float)
        return Image.fromarray(np.clip(a + np.random.default_rng(1).normal(0, sd, a.shape), 0, 255).astype("uint8"))
    return f


def shade(im):
    a = np.asarray(im.convert("RGB"), float)
    return Image.fromarray((a * np.linspace(1, .55, a.shape[1])[None, :, None]).astype("uint8"))


def as_pdf(im):
    b = io.BytesIO(); im.convert("RGB").save(b, "PDF", resolution=150); b.seek(0); return open_upload(b)[0][0]


def perspective(im):
    w, h = im.size
    return im.convert("RGB").transform((w, h), Image.PERSPECTIVE, (1, .02, -10, .01, 1, -10, 1e-5, 1e-5), Image.BICUBIC, fillcolor="white")


FORMS = {"as sent": lambda i: i, "jpeg 70": jpeg(70), "jpeg 30": jpeg(30), "jpeg 12": jpeg(12), "75% size": scale(.75), "50% size": scale(.5), "35% size": scale(.35), "150% size": scale(1.5),
         "tilt +3": turn(3), "tilt -7": turn(-7), "tilt +11": turn(11), "tilt +20": turn(20), "sideways 90": turn(90), "upside down": turn(180), "sideways 270": turn(270),
         "dim": bright(.5), "low contrast": lambda i: ImageEnhance.Contrast(i.convert("RGB")).enhance(.45), "blur 1": blur(1), "blur 2": blur(2), "blur 4": blur(4),
         "grain 15": grain(15), "grain 40": grain(40), "shadow": shade, "perspective": perspective, "greyscale": lambda i: i.convert("L"), "transparency": lambda i: i.convert("RGBA"), "pdf": as_pdf}


def degrade(job):
    k, name = job
    try:
        return k, name, verify_images({d: FORMS[name](x) for d, x in load_specimen(k).items()}).verdict
    except Exception as e:
        return k, name, f"CRASH {e!r}"


def gstin_line(img):
    ink = _ink(img); d = pytesseract.image_to_data(ink, config="--psm 6", output_type=pytesseract.Output.DICT)
    i = next(i for i, t in enumerate(d["text"]) if t.strip().upper().startswith("GSTIN"))
    y, h, left = d["top"][i], d["height"][i], d["left"][i] + d["width"][i] + 10
    xs = np.where((np.asarray(ink) < 128)[max(y - 6, 0):y + h + 8, left:].any(axis=0))[0]
    gaps = np.where(np.diff(xs) > 30)[0]
    return left + xs.min(), left + (xs[gaps[0]] if len(gaps) else xs[-1]), max(y - 6, 0), y + h + 8


def forge(job):
    k, p, q = job
    s = load_specimen(k); img = s["gst"].convert("RGB")
    x0, x1, y0, y1 = gstin_line(img); pitch = (x1 - x0 + 1) / 15
    box = lambda n: (round(x0 + n * pitch), y0, round(x0 + (n + 1) * pitch), y1)
    img.paste(img.crop(box(q)).resize((box(p)[2] - box(p)[0], y1 - y0)), box(p)[:2])
    forms = {"straight": img, "dim": bright(.5)(img), "tilted": turn(3)(img), "pdf": as_pdf(img)}
    return k, p, {n: verify_images({**s, "gst": x}).verdict for n, x in forms.items()}


def forgeries():
    jobs = []
    for k, t in STRAIGHT_CLEAN.items():
        can = registry.canon(t)
        for p in range(2, 14):
            qs = [q for q in range(15) if can[q] != can[p] and t[q].isdigit()]
            if qs: jobs.append((k, p, qs[(p * 3) % len(qs)]))
    return jobs


if __name__ == "__main__":
    with Pool(max((os.cpu_count() or 2) - 1, 1)) as pool:
        runs = pool.map(degrade, [(k, n) for k in SPECIMEN_REVIEW for n in FORMS], chunksize=2)
        forged = pool.map(forge, forgeries())
    bad = [r for r in runs if r[2].startswith("CRASH") or (r[0] in CLEAN and r[2] == "rejected") or (r[0] not in CLEAN and r[2] == "verified")]
    print(f"Degraded uploads: {len(runs)} runs, {len(bad)} wrong"); [print(" ", b) for b in bad]
    print(f"{'form':14} clean applicants verified of {len(CLEAN)}")
    for n in FORMS: print(f"{n:14} {sum(r[1] == n and r[0] in CLEAN and r[2] == 'verified' for r in runs)}")
    tally = Counter((n, v) for _, _, res in forged for n, v in res.items()); slipped = sum(v == "verified" for (_, v), c in tally.items() for _ in range(c))
    print(f"Forgeries: {len(forged)} x 4 forms, {slipped} verified"); [print(" ", k, v) for k, v in sorted(tally.items())]
    sys.exit(1 if bad or slipped else 0)
