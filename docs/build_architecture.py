"""Draws docs/architecture.png, matching the flow in architecture.md. Run: python docs/build_architecture.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
F = "/System/Library/Fonts/Supplemental/Arial.ttf"; FB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
W, H = 2000, 1300
im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
f, fb, ft = ImageFont.truetype(F, 24), ImageFont.truetype(FB, 27), ImageFont.truetype(FB, 40)
INK, LINE, CODE, EXT, STORE, USER = "#1f2933", "#52606d", "#e3f2fd", "#fff3e0", "#e8f5e9", "#f3e5f5"
def box(x, y, w, h, title, sub="", fill=CODE):
    d.rounded_rectangle((x, y, x + w, y + h), 14, fill=fill, outline=LINE, width=2)
    d.text((x + w / 2, y + 16), title, font=fb, fill=INK, anchor="ma")
    for i, l in enumerate(sub.split("\n") if sub else []):
        d.text((x + w / 2, y + 54 + i * 30), l, font=f, fill=INK, anchor="ma")
def arrow(a, b, label="", dash=False, off=(10, -32)):
    (x1, y1), (x2, y2) = a, b
    n = max(abs(x2 - x1), abs(y2 - y1)) or 1
    if dash:
        for i in range(0, int(n), 22):
            j = min(i + 12, n)
            d.line((x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n, x1 + (x2 - x1) * j / n, y1 + (y2 - y1) * j / n), fill=LINE, width=3)
    else:
        d.line((x1, y1, x2, y2), fill=LINE, width=3)
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    d.polygon([(x2, y2), (x2 - 16 * ux - 8 * uy, y2 - 16 * uy + 8 * ux), (x2 - 16 * ux + 8 * uy, y2 - 16 * uy - 8 * ux)], fill=LINE)
    if label: d.text(((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1]), label, font=f, fill=LINE)
d.text((W / 2, 28), "Udyam Digital: main components and data flows", font=ft, fill=INK, anchor="ma")
box(700, 95, 600, 130, "Streamlit pages (phone browser)", "Advisor · Quote · Consent · KYC · Tracker", USER)
box(80, 320, 520, 170, "Advisor flow", "advisor.py: asks at most 6 questions,\nanswers from catalogue facts", CODE)
box(80, 580, 520, 170, "Guardrails", "Redact identifiers before anything else;\ncheck every reply's products and prices", CODE)
box(80, 850, 520, 150, "LLM API (optional)", "Redacted text in; profile fields\nand wording out. Never images or IDs", EXT)
box(720, 320, 560, 170, "Rules and pricing", "rules.py: eligibility, dependencies, smallest\nbundle. pricing.py: server-side price", CODE)
box(720, 580, 560, 170, "Consent and orders", "Per-purpose consent, withdrawal;\norder stages for the tracker", CODE)
box(1400, 320, 520, 170, "Smart KYC", "Tesseract OCR in memory, validators,\ncross-checks; three verdicts", CODE)
box(720, 850, 560, 150, "Product catalogue", "product_catalogue.csv (25 products)", STORE)
box(1400, 850, 520, 150, "Mock registries", "GSTIN and Udyam CSV lookups", STORE)
box(720, 1090, 560, 150, "SQLite", "Masked fields, verdicts, consent, orders,\nhand-off summaries. No raw documents", STORE)
arrow((800, 225), (400, 320)); arrow((1000, 225), (1000, 320)); arrow((1200, 225), (1600, 320), "document images, memory only", off=(30, -40))
arrow((340, 490), (340, 580)); arrow((270, 750), (270, 850), "redacted text", True, off=(-175, -14))
arrow((410, 850), (410, 750), "fields, wording", True, off=(10, -14))
arrow((600, 405), (720, 405))
arrow((1000, 490), (1000, 580), "accepted quote")
d.line((1280, 440, 1330, 440), fill=LINE, width=3); d.line((1330, 440, 1330, 925), fill=LINE, width=3); arrow((1330, 925), (1280, 925))
arrow((1660, 490), (1660, 850), "lookups"); arrow((1450, 490), (1280, 680), "verdict", off=(-5, 30))
d.line((720, 700, 670, 700), fill=LINE, width=3); d.line((670, 700, 670, 1165), fill=LINE, width=3); arrow((670, 1165), (720, 1165))
d.line((600, 470, 670, 470), fill=LINE, width=3); d.line((670, 470, 670, 700), fill=LINE, width=3)
d.text((605, 500), "hand-off", font=f, fill=LINE)
d.rectangle((80, 1090, 600, 1240), outline=LINE, width=1)
d.text((100, 1105), "Key choice", font=fb, fill=INK)
d.text((100, 1145), "Code decides every product and price. The", font=f, fill=INK)
d.text((100, 1175), "advisor still works if the LLM is unavailable.", font=f, fill=INK)
im.save(Path(__file__).with_name("architecture.png"))
