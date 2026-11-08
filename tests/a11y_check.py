"""Accessibility audit (WCAG 2.1 A and AA, with axe-core) of every page and the states that only appear after an action.
Starts its own server with a throwaway database. Needs, beyond requirements.txt:

    pip install playwright axe-playwright-python && playwright install chromium

Run: python tests/a11y_check.py      (exits non-zero if anything fails)"""
from __future__ import annotations
import os, pathlib, socket, subprocess, sys, tempfile, time
import axe_playwright_python
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
AXE = os.path.join(os.path.dirname(axe_playwright_python.__file__), "axe.min.js")
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
H = {"X-Requested-With": "udyam"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), tempfile.mkdtemp()
    env = {**os.environ, "UDYAM_DB": os.path.join(tmp, "a11y.db"), "LLM_API_KEY": "", "AB_TEST": "off", "PARTNER_PASSCODE": ""}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.server:app", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    U, found = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try:
                import urllib.request; urllib.request.urlopen(U + "/healthz", timeout=1); break
            except OSError: time.sleep(.5)
        with sync_playwright() as p:
            try: b = p.chromium.launch(channel="chrome")
            except Exception: b = p.chromium.launch()

            def audit(pg, name):
                pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                pg.add_script_tag(path=AXE)
                res = pg.evaluate("async (t) => (await axe.run(document, {runOnly: {type: 'tag', values: t}})).violations.map(v => [v.id, v.impact, v.nodes.length])", TAGS)
                print(f"{'ok  ' if not res else 'FAIL'} {name}" + (f": {res}" if res else ""), flush=True)
                found.extend(res)

            pg = b.new_context(bypass_csp=True, viewport={"width": 390, "height": 844}).new_page(); r = pg.context.request
            def go(path): pg.goto(U + path); pg.wait_for_load_state("networkidle"); time.sleep(.3)
            go("/"); audit(pg, "home")
            go("/tracker"); audit(pg, "tracker: Find my order (empty)")
            f = pg.locator("#find"); f.locator("input").nth(0).fill("1"); f.locator("input").nth(1).fill("9000000000"); f.locator("input").nth(1).press("Enter")
            pg.wait_for_selector("#find .note.danger"); audit(pg, "tracker: Find my order error")
            r.post(U + "/api/advisor/message", data={"text": "Clinic in Delhi, 6 staff, one location, have GSTIN, want email"}, headers=H)
            go("/advisor"); audit(pg, "advisor with a plan")
            pg.get_by_role("button", name="Talk to a person").first.click(); time.sleep(.3); audit(pg, "advisor: Talk to a person open")
            go("/quote"); audit(pg, "quote")
            r.post(U + "/api/quote/accept", data={}, headers=H)
            go("/consent"); audit(pg, "consent before ticking")
            r.post(U + "/api/consent", data={"kyc": True, "updates": True}, headers=H)
            r.post(U + "/api/contact", data={"name": "Ravi Kumar", "phone": "9876543210", "agree": True}, headers=H)
            go("/consent"); audit(pg, "consent after saving")
            r.post(U + "/api/kyc/verify", data={"mode": "specimen", "applicant": "K03"}, headers=H)
            for _ in range(150):
                if (r.get(U + "/api/view/kyc").json() or {}).get("result"): break
                time.sleep(1)
            go("/kyc"); audit(pg, "kyc result")
            go("/tracker"); audit(pg, "tracker with an order")
            go("/data"); audit(pg, "your data")
            oid = str(r.get(U + "/api/view/tracker").json()["order"])
            other = b.new_context(bypass_csp=True, viewport={"width": 390, "height": 844}).new_page()
            other.goto(U + "/tracker"); other.wait_for_selector("#find")
            g = other.locator("#find"); g.locator("input").nth(0).fill(oid); g.locator("input").nth(1).fill("9876543210"); g.locator("input").nth(1).press("Enter")
            other.wait_for_selector("#find .code"); audit(other, "tracker: Find my order code step")
            st = b.new_context(bypass_csp=True, viewport={"width": 1280, "height": 900}).new_page()
            st.goto(U + "/partner"); st.wait_for_selector("[role=tablist]")
            for tab in ["Live dashboard", "KYC review", "Leads and routing", "Payback what-if", "Logs", "Evidence"]:
                st.get_by_role("tab", name=tab).click(); time.sleep(.5); audit(st, "staff: " + tab)
            st.get_by_role("button", name="Rerun advisor scenarios and security probes").click()
            st.wait_for_selector("text=All checks passed.", timeout=180000); audit(st, "staff: Evidence results")
            b.close()
    finally:
        srv.terminate()
    print(f"\n{'0 violations' if not found else str(len(found)) + ' violation types'} across every page and state checked")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
