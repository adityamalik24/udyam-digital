"""Shares the app from this laptop on a public https link through ngrok (free account, no card). Run from the repo root:

    .venv/bin/python deploy/share_ngrok.py

Needs, in .env (gitignored): NGROK_AUTHTOKEN (from the ngrok dashboard) and SPACE_PARTNER_PASSCODE (the staff
passcode, 8+ characters; the name is kept from the Hugging Face attempt). LLM_API_KEY is used as usual.

Public mode differs from a plain local run in two ways: /partner needs the passcode, and every visitor sees the
same quote layout (AB_TEST=off). The Mac is kept awake while this runs; closing the lid on battery still sleeps it.
Stop with Ctrl+C, which stops both the app and the link.
"""
from __future__ import annotations
import json, os, pathlib, signal, socket, subprocess, sys, time, urllib.request
from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8000


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def public_url(deadline: float) -> str | None:
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
                for t in json.load(r).get("tunnels", []):
                    if t.get("public_url", "").startswith("https://"): return t["public_url"]
        except OSError:
            pass
        time.sleep(1)
    return None


def main() -> None:
    env_file = {k: (v or "").strip() for k, v in dotenv_values(ROOT / ".env").items()}
    token, code = env_file.get("NGROK_AUTHTOKEN", ""), env_file.get("SPACE_PARTNER_PASSCODE", "")
    if not token or not code: sys.exit("Add NGROK_AUTHTOKEN and SPACE_PARTNER_PASSCODE to .env first.")
    if len(code) < 8: sys.exit("SPACE_PARTNER_PASSCODE should be at least 8 characters.")
    if port_busy(PORT): sys.exit(f"Something is already running on port {PORT}. Stop your local server first, then run this again.")

    app_env = {**os.environ, "PARTNER_PASSCODE": code, "AB_TEST": "off"}
    app = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.server:app", "--port", str(PORT), "--workers", "1",
                            "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"], cwd=ROOT, env=app_env)
    tunnel = subprocess.Popen(["ngrok", "http", str(PORT), "--log", "false"], env={**os.environ, "NGROK_AUTHTOKEN": token},
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    stop = lambda *_: (tunnel.terminate(), app.terminate(), awake.terminate(), sys.exit(0))
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)

    url = public_url(time.time() + 30)
    if not url:
        stop_msg = "The ngrok link didn't start. Check NGROK_AUTHTOKEN, and that no other ngrok is running."
        tunnel.terminate(); app.terminate(); awake.terminate(); sys.exit(stop_msg)
    print(f"\nPublic link: {url}\nStaff view:  {url}/partner  (passcode from .env)\n"
          "Visitors click 'Visit Site' once on ngrok's notice. Keep this window open; Ctrl+C stops sharing.\n", flush=True)
    while app.poll() is None and tunnel.poll() is None: time.sleep(2)
    stop()


if __name__ == "__main__":
    main()
