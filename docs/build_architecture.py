"""Draws docs/architecture.png, matching the flow in architecture.md. Run: python docs/build_architecture.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
F = "/System/Library/Fonts/Supplemental/Arial.ttf"; FB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
W, H = 2120, 1500
im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
f, fb, ft = ImageFont.truetype(F, 23), ImageFont.truetype(FB, 26), ImageFont.truetype(FB, 40)
INK, LINE, CODE, EXT, STORE, USER, SERVER = "#1f2933", "#52606d", "#e3f2fd", "#fff3e0", "#e8f5e9", "#f3e5f5", "#ede7f6"
COL = [60, 570, 1080, 1590]; CW = 470          # four columns
R1, R2, R3, R4 = 280, 520, 790, 1060          # row tops


def box(x, y, w, h, title, sub="", fill=CODE):
    d.rounded_rectangle((x, y, x + w, y + h), 14, fill=fill, outline=LINE, width=2)
    d.text((x + w / 2, y + 16), title, font=fb, fill=INK, anchor="ma")
    for i, l in enumerate(sub.split("\n") if sub else []):
        d.text((x + w / 2, y + 54 + i * 29), l, font=f, fill=INK, anchor="ma")


def line(*pts):
    d.line(pts, fill=LINE, width=3)


def arrow(a, b, label="", dash=False, off=(10, -30)):
    (x1, y1), (x2, y2) = a, b
    n = max(abs(x2 - x1), abs(y2 - y1)) or 1
    if dash:
        for i in range(0, int(n), 22):
            j = min(i + 12, n)
            d.line((x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n), fill=LINE, width=3)
    else:
        line(x1, y1, x2, y2)
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    d.polygon([(x2, y2), (x2 - 16 * ux - 8 * uy, y2 - 16 * uy + 8 * ux), (x2 - 16 * ux + 8 * uy, y2 - 16 * uy - 8 * ux)], fill=LINE)
    if label: d.text(((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1]), label, font=f, fill=LINE)


d.text((W / 2, 24), "Udyam Digital: main components and data flows", font=ft, fill=INK, anchor="ma")

# Who uses it
box(60, 90, 980, 120, "Owner's phone browser (web/static)", "Advisor (type or speak) · Quote · Consent · KYC · Tracker · Your data", USER)
box(1080, 90, 980, 120, "Staff browser: Partner queue (/partner)", "Dashboard · KYC review · Leads to call · Money · Logs (optional passcode)", USER)

# The server
box(60, R1, 1490, 160, "web/server.py (FastAPI)", "One session per browser. Takes choices, never a price, verdict or total: it recomputes them.\nChecks every order belongs to the session. Strict CSP, request-header check, heavy work off the main loop.", SERVER)
box(COL[3], R1, CW, 160, "Insights and lead scoring", "Payback, churn watchlist, routing,\ndropped-lead scores (AUC 0.71), A/B", CODE)

# Core modules (core/)
box(COL[0], R2, CW, 190, "Advisor and guardrails", "Redacts IDs first; at most 6 questions;\nEnglish, Hindi, Hinglish; every reply's\nproducts and prices checked", CODE)
box(COL[1], R2, CW, 190, "Rules and pricing", "Eligibility, dependencies, smallest\nbundle, one cheaper option.\nServer-side price (midpoint)", CODE)
box(COL[2], R2, CW, 190, "Smart KYC", "Tesseract OCR in memory, validators,\ncross-checks, file-edit signs.\nverified / needs_review / rejected", CODE)
box(COL[3], R2, CW, 190, "Mock registries", "GSTIN and Udyam lookups\n(CSV stand-ins for the real APIs)", STORE)

box(COL[0], R3, CW, 190, "LLM: Gemini (optional)", "Redacted text in; profile fields and\nwording out. Speech only with its own\nconsent. Never images or ID numbers", EXT)
box(COL[1], R3, CW, 190, "Orders and tracker", "7 stages with timestamps,\nnext expected date, technician,\nreschedule", CODE)
box(COL[2], R3, CW, 190, "Consent, contact, data rights", "Separate unticked box per purpose;\nwithdraw, download, correct, erase.\nName and phone before payment", CODE)
box(COL[3], R3, CW, 190, "Maker-checker review", "Two staff sign off before a\nneeds_review case is decided", CODE)

# Stores
box(COL[0], R4, CW, 150, "Product catalogue", "product_catalogue.csv\n(25 products)", STORE)
box(COL[1], R4, 980, 150, "SQLite", "Masked IDs, verdicts, consent records, orders, contacts,\nreviews, hand-off summaries, audit log. No raw documents", STORE)
box(COL[3], R4, CW, 150, "smb_leads.csv", "5,000 past leads: segments,\ndrop reasons, churn, cost", STORE)

# Flows
arrow((550, 210), (550, R1)); arrow((1570, 210), (1300, R1))
for x in COL[:3]: arrow((x + CW / 2, R1 + 160), (x + CW / 2, R2))
arrow((1550, R1 + 80), (COL[3], R1 + 80))
arrow((COL[0] + 150, R2 + 190), (COL[0] + 150, R3), "redacted text", True, off=(-140, -12))
arrow((COL[0] + 320, R3), (COL[0] + 320, R2 + 190), "fields, wording", True, off=(14, -12))
arrow((COL[0] + CW, R2 + 95), (COL[1], R2 + 95))
arrow((COL[1] + CW / 2, R2 + 190), (COL[1] + CW / 2, R3), "accepted quote", off=(12, -14))
line(COL[1], R2 + 160, 550, R2 + 160); line(550, R2 + 160, 550, R4 + 75); arrow((550, R4 + 75), (COL[0] + CW, R4 + 75))
arrow((COL[2] + 120, R2 + 190), (COL[1] + CW - 40, R3), "verdict", off=(-30, -36))
arrow((COL[2] + 340, R3), (COL[2] + 340, R2 + 190), "consent first", off=(12, -14))
arrow((COL[2] + CW, R2 + 70), (COL[3], R2 + 70))
arrow((COL[2] + CW, R2 + 165), (COL[3], R3 + 70))
d.text((COL[3] + 20, R2 + 200), "unsure cases", font=f, fill=LINE)
arrow((COL[1] + CW / 2, R3 + 190), (COL[1] + CW / 2, R4)); arrow((COL[2] + CW / 2, R3 + 190), (COL[2] + CW / 2, R4))
arrow((COL[3], R3 + 170), (COL[1] + 980, R4 + 30))
line(COL[3] + CW, R4 + 75, 2095, R4 + 75); line(2095, R4 + 75, 2095, R1 + 120); arrow((2095, R1 + 120), (COL[3] + CW, R1 + 120))

# Key choice
d.rectangle((60, 1260, 2060, 1460), outline=LINE, width=1)
d.text((80, 1275), "Key choices", font=fb, fill=INK)
for i, t in enumerate(["Code decides every product and price; the LLM only reads messages and words replies around slots code fills. The advisor works with the LLM off.",
                       "KYC never sends images or ID numbers to the LLM, deletes uploads after the check, and sends anything uncertain to a person instead of rejecting it.",
                       "The browser only sends choices. Prices, verdicts and order totals are recomputed on the server, and staff screens show contact details masked."]):
    d.text((80, 1318 + i * 42), "• " + t, font=f, fill=INK)
im.save(Path(__file__).with_name("architecture.png"))
