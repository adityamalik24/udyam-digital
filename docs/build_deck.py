"""Builds docs/Udyam_Digital_Business_Case.pptx on the hackathon template. Prices come from core.pricing."""
import io, sys, pathlib
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from pptx import Presentation
from pptx.util import Inches as I, Pt
from pptx.dml.color import RGBColor as RGB
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from core.pricing import price
TEMPLATE = sys.argv[1]
RED, INK, MUTE, TINT, WHITE = RGB(0xC8,0,0x0F), RGB(0x22,0x22,0x22), RGB(0x59,0x59,0x59), RGB(0xFB,0xEC,0xEC), RGB(255,255,255)
p = Presentation(TEMPLATE)
bg = [next(x for x in s.shapes if x.shape_type == 13).image.blob for s in p.slides]
layout = next(l for l in p.slide_layouts if l.name == "TITLE_ONLY")

def text(s, x, y, w, h, runs, size=13, color=INK, bold=False, anchor=None):
    b = s.shapes.add_textbox(I(x), I(y), I(w), I(h)); tf = b.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if anchor: tf.vertical_anchor = anchor
    for i, r in enumerate([runs] if isinstance(runs, str) else runs):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(5)
        rn = para.add_run(); rn.text = r; rn.font.size = Pt(size); rn.font.color.rgb = color; rn.font.bold = bold; rn.font.name = "Calibri"
    return b

def slide(title):
    s = p.slides.add_slide(layout)
    pic = s.shapes.add_picture(io.BytesIO(bg[1]), 0, 0, p.slide_width, p.slide_height)
    s.shapes._spTree.remove(pic._element); s.shapes._spTree.insert(2, pic._element)
    t = s.shapes.title; t.left, t.top, t.width, t.height = I(1.3), I(0.12), I(7.4), I(0.62)
    t.text_frame.word_wrap = True; t.text_frame.text = title; t.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = t.text_frame.paragraphs[0].runs[0]; r.font.size = Pt(19); r.font.bold = True; r.font.color.rgb = INK; r.font.name = "Calibri"
    return s

def card(s, x, y, w, h, head, body, hs=22, bs=11):
    c = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, I(x), I(y), I(w), I(h)); c.adjustments[0] = .06
    c.fill.solid(); c.fill.fore_color.rgb = TINT; c.line.fill.background(); c.shadow.inherit = False
    text(s, x+.1, y+.07, w-.2, .4, head, hs, RED, True); text(s, x+.1, y+.07+hs/72*1.25, w-.2, h-.5, body, bs, INK)

def table(s, x, y, w, rows, widths, size=11, rh=.3):
    g = s.shapes.add_table(len(rows), len(rows[0]), I(x), I(y), I(w), I(rh*len(rows))).table
    tot = sum(widths)
    for j, wd in enumerate(widths): g.columns[j].width = I(w*wd/tot)
    for i, row in enumerate(rows):
        g.rows[i].height = I(rh)
        for j, v in enumerate(row):
            c = g.cell(i, j); c.text = str(v); c.margin_left = c.margin_right = I(.05); c.margin_top = c.margin_bottom = I(.02); c.vertical_anchor = MSO_ANCHOR.MIDDLE
            f = c.text_frame.paragraphs[0].runs[0].font if c.text_frame.paragraphs[0].runs else None
            c.fill.solid(); c.fill.fore_color.rgb = RED if i == 0 else (TINT if i % 2 == 0 else WHITE)
            if f: f.size, f.name, f.bold = Pt(size), "Calibri", i == 0; f.color.rgb = WHITE if i == 0 else INK

def bars(s, x, y, w, h, cats, vals, title, kind=XL_CHART_TYPE.BAR_CLUSTERED, fmt="#,##0", vmax=None):
    if kind == XL_CHART_TYPE.BAR_CLUSTERED: cats, vals = cats[::-1], vals[::-1]  # bar charts plot bottom-up
    d = CategoryChartData(); d.categories = cats; d.add_series(title, vals)
    ch = s.shapes.add_chart(kind, I(x), I(y), I(w), I(h), d).chart
    ch.has_legend = False; ch.has_title = True; ch.chart_title.text_frame.text = title
    f = ch.chart_title.text_frame.paragraphs[0].runs[0].font; f.size = Pt(12); f.bold = True; f.color.rgb = INK
    pl = ch.plots[0]; pl.gap_width = 45; pl.has_data_labels = True; dl = pl.data_labels
    dl.number_format, dl.number_format_is_linked, dl.position, dl.show_value = fmt, False, XL_LABEL_POSITION.OUTSIDE_END, True; dl.font.size = Pt(11)
    pl.series[0].format.fill.solid(); pl.series[0].format.fill.fore_color.rgb = RED
    ch.value_axis.visible = False; ch.value_axis.has_major_gridlines = False
    ch.category_axis.tick_labels.font.size = Pt(11); ch.category_axis.format.line.color.rgb = MUTE
    ch.value_axis.minimum_scale = 0
    if vmax: ch.value_axis.maximum_scale = vmax

# 1 Title (template slide 1)
s1 = p.slides[0]
text(s1, .65, 2.75, 3.6, .5, "Udyam Digital", 26, WHITE, True)
text(s1, .65, 3.3, 3.5, .9, ["A small business goes digital in one sitting, on a phone", "Team RNG. Enterprise Track A: business case"], 13, WHITE)

# 2 Problem
s = slide("Only 7.4% of small-business leads activate, at ₹15,053 each")
bars(s, .5, .8, 5.1, 3.85, ["Leads","Contacted","Needs assessed","Quote accepted","KYC complete","Activated"], [5000,3406,1974,861,588,368], "Funnel, Apr to Jun 2026")
card(s, 5.8, .85, 3.5, 1.15, "17.6 days", "average from lead to activation, with about 3 status-chase calls per customer")
card(s, 5.8, 2.15, 3.5, 1.15, "8 months", "to pay back acquisition on a micro customer: ₹20,007 cost against ₹2,505 a month")
card(s, 5.8, 3.45, 3.5, 1.15, "1,338 drops", "cite visits, slow or complex quotes, or paperwork: the steps a digital journey replaces")

# 3 Where it breaks
s = slide("The drop reasons we can remove are about process, not demand")
table(s, .5, .9, 8.8, [["Stage","Drop reason","Leads","Our fix"],
 ["Contacted","No time for a visit / visit not scheduled","827","No visit: chat advisor on a phone"],
 ["Needs assessed","Quote too complex / took too long","385","Instant quote, one price, no codes"],
 ["Quote accepted","Paperwork too long / details did not match","126","Consent, OCR and registry checks in minutes"],
 ["KYC complete","Installation delayed beyond 21 days","98","Tracker now; delivery capacity still needed"],
 ["Needs assessed","Price too high / competitor cheaper","621","Not solved: smallest bundle only helps partly"]], [1.5,3.5,.75,3.35], 12, .42)
text(s, .5, 3.65, 8.8, .9, ["Price is the largest single reason at the quote stage (621 of 1,113 drops). We don't claim to fix it: the advisor avoids upselling and shows a cheaper option, but cannot discount.",], 13)

# 4 Segments
s = slide("Prioritise professional offices first, then multi-site")
table(s, .5, .9, 8.8, [["Segment","Leads","Activate","₹/month","6-mo churn","Cost per activation","Payback"],
 ["Professional offices","1,247","11.1%","6,796","13.8%","₹10,695","1.6 mo"],
 ["Small multi-site","755","11.0%","31,233","10.8%","₹15,614","0.5 mo"],
 ["Small manufacturers","289","12.8%","19,980","8.1%","₹15,324","0.8 mo"],
 ["Micro retail and services","2,709","4.1%","2,505","22.7%","₹20,007","8.0 mo"]], [2.6,.7,.9,.9,1,1.6,.9], 12, .38)
text(s, .5, 3,8.8,1.7, ["Professional offices: largest high-value pool, cheapest to acquire, and the journey runs fully self-serve.",
 "Multi-site and manufacturers: highest value, but they need specialists. The advisor qualifies, then hands off with a summary.",
 "Micro: 54% of leads. Field visits here took 25.8% of all spend for 7.3% of activations (₹53,026 each), so serve them digital-only."], 13)

# 5 Bundles
def m(items):
    q = price(items); return f"₹{q.monthly:,}", f"₹{q.setup:,}", f"{q.contract} months"
s = slide("One clear monthly price for each segment")
B = [("Kirana, no GSTIN","Biz 5G AirFiber 100",{"P04":1}),
     ("Clinic, 6 staff","Biz Fibre 100, Cloud Email × 6, Endpoint Security × 6",{"P01":1,"P16":6,"P20":6}),
     ("Restaurant, 4 outlets","Biz Fibre 300, Failover, Cloud CCTV and SD-WAN, per outlet",{"P02":4,"P09":4,"P23":4,"P10":4}),
     ("Textile unit, 40 staff","Leased Line 20, Machine Monitoring IoT × 2",{"P05":1,"P24":2})]
table(s, .5, .9, 8.8, [["Example customer","Bundle","Monthly","Setup","Contract"]]+[[a,b,*m(c)] for a,b,c in B], [1.9,4.2,.9,.9,1], 12, .5)
text(s, .5, 3.6, 8.8, 1, ["Each price is the midpoint of the catalogue range; activated leads paid 0.48 of the way through it on average, with no gap by tier or segment. Examples are computed by the same pricing engine the app uses."], 13)

# 6 Product
s = slide("A working journey where code, not the LLM, decides")
for i,(h,b) in enumerate([("Advisor","English, Hindi, Hinglish, typed or spoken. At most 6 questions, no upsell"),("Quote","One price, recomputed on the server; the chat stays open to change it"),("Smart KYC","Consent first. OCR, checksums, registry checks, file-edit signs"),("Tracker","7 stages with timestamps, reschedule; download or erase your data")]):
    card(s, .5+i*2.23, .9, 2.1, 1.55, h, b, 16, 12)
text(s, .5, 2.6, 8.8, 2.1, ["The LLM reads messages and words replies around slots that code fills, so it can't type a price or product name in any language.",
 "Tested on our own cases, not the judges': 243 of 243 advisor scenarios pass in English, Hindi and Hinglish, and no eligibility or price breaks across 303,408 business profiles. All 12 KYC applicants match our manual review (5 verified, 5 needs review, 2 rejected), and 0 of 192 forged certificates verified.",
 "For staff: unsure KYC cases need two people to sign off, dropped leads are ranked for a call-back (AUC 0.71 on held-out folds), and a churn watchlist flags orders to check in on.",
 "Identifiers are stripped from chat before storage. Document images stay in memory and never reach the LLM."], 12)

# 7 Signals
s = slide("Customers who chase status more churn more")
bars(s, .5, .8, 4.6, 3.85, ["1","2","3","4","5"], [5.9,14.3,11.7,20.0,27.9], "6-month churn (%) by number of status-chase calls", XL_CHART_TYPE.COLUMN_CLUSTERED, "0.0", vmax=35)
text(s, 5.3, .95, 4, 3.7, ["NPS also falls from 7.5 to 6.0 across the same range (p<0.001). This is a correlation, so a pilot should test it.",
 "56 of 368 activated bundles broke a catalogue rule, and 22 activations sit on a cancelled or suspended GSTIN. Enforcing rules in code stops both.",
 "Referral converts best (14.8%), WhatsApp campaigns worst (2.8%).",
 "Hotspot users churn at 24.7% against 8.3% on business broadband (p=0.002).",
 "GSTIN: 9.6% activate against 2.0% without, and the gap holds within micro (6.3% against 1.6%)."], 12)

# 8 Value
s = slide("Recovering half of process drops takes activation to about 11%")
bars(s, .5, .8, 4.8, 3.85, ["Today","No visit needed","Instant quote","Faster KYC"], [368,77,82,39], "Activations per quarter, and what each fix adds")
card(s, 5.5, .85, 3.8, 1.15, "368 to 566", "activations per quarter, from the same 5,000 leads (7.4% to 11.3%)")
card(s, 5.5, 2.15, 3.8, 1.15, "Assumption", "50% recovery is our estimate, not data. 30% gives 487 activations and 70% gives 645", 16, 12)
card(s, 5.5, 3.45, 3.8, 1.15, "To validate", "Pilot measures real recovery, and our build and run costs still need to be set against it", 16, 12)

# 9 Rollout + metrics
s = slide("Roll out in three steps, and measure five numbers")
table(s, .5, .88, 4.2, [["Phase","Scope"],["1. Pilot","Professional offices, Tier 1, Hindi and English, starting with Accel mobile customers (9.2% activate)"],["2. Extend","Micro digital-only, Tier 2, and regional languages, starting with Tamil and Punjabi (about 4%)"],["3. Assisted","Multi-site and manufacturers via specialists"]], [1,3], 12, .5)
text(s, .5, 3.3, 4.2, 1.45, ["Field force: off micro and onto complex accounts and hand-offs, which arrive with a saved summary.","Partners: keep credit for their leads, run installs, and call a ranked queue of dropped leads (the top tenth activate at 2.2 times the average)."], 13)
table(s, 4.95, .88, 4.35, [["Metric","Now","Target"],["Lead to activation","7.4%","11%"],["Days to activate","17.6","10"],["Status chases","3.0","1 or fewer"],["Cost per activation","₹15,053","₹10,000"],["Micro 6-month churn","22.7%","15%"]], [2.3,1,1], 12, .42)
text(s, 4.95, 3.55, 4.35, .8, "Targets are our proposals. Keep at zero: rule-breaking bundles (56 today), activations on an inactive GSTIN (22), and false KYC rejections.", 12, MUTE)

# 10 Risks
s = slide("Main risks, and what we are asking for")
table(s, .5, .9, 8.8, [["Risk","Mitigation"],
 ["Advisor gives a wrong plan or price","Rules engine decides; replies are validated; regression scenarios run before release"],
 ["KYC wrongly rejects a real business","Rejection needs hard evidence; anything uncertain goes to a person"],
 ["Personal data exposure (DPDP Act)","Per-purpose consent, masked fields, images not retained, withdrawal in tracker"],
 ["Install capacity limits the gains","98 drops are install delays; tracker doesn't fix capacity. Indore and Mysuru take 8+ days from KYC to activation vs 4.8 overall (under 10 customers each, so verify)"],
 ["Channel conflict with partners","Partners keep attribution and install work; specialists get hand-offs"]], [3,5.8], 12, .42)
text(s, .5, 3.65, 8.8, .9, "Ask: approve a pilot in professional offices, Tier 1 cities, with real registry access, then decide on Phase 2 from measured recovery.", 14, RED, True)

# Move the blank template content slide out: it held only the background
ids = p.slides._sldIdLst; el = list(ids)[1]; p.part.drop_rel(el.rId); ids.remove(el)
out = ROOT / "docs" / "Udyam_Digital_Business_Case.pptx"; p.save(out); print(out, len(p.slides))
