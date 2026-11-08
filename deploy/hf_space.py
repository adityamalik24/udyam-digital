"""Publishes the web app to a free Hugging Face Space (Docker). Run from the repo root:

    python deploy/hf_space.py [space-name]        # default name: udyam-digital

Needs, in .env or the environment (never in a file that is committed):
    HF_TOKEN                a Hugging Face access token with write permission
    LLM_API_KEY             the Gemini key, stored as a private Space secret
    SPACE_PARTNER_PASSCODE  the staff passcode for /partner on the Space (a different name from PARTNER_PASSCODE,
                            so the local app stays open on your laptop)

It uploads only committed files the image needs (Dockerfile, requirements-web.txt, core/, data/, web/) plus a Space
README, and replaces whatever the Space held before. Keys go in as Space secrets, so they never appear in the Space's files.
"""
from __future__ import annotations
import os, pathlib, shutil, subprocess, sys, tempfile
from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = pathlib.Path(__file__).resolve().parents[1]
NEED = ("Dockerfile", "requirements-web.txt", "core/", "data/", "web/")
SKIP_NAMES = {"lead_scores.json", ".DS_Store"}  # the image builds the scores itself
README = """---
title: Udyam Digital
emoji: 📶
colorFrom: red
colorTo: gray
sdk: docker
app_port: 10000
pinned: false
short_description: Telecom plans for small businesses, one clear monthly price
---

# Udyam Digital

A mobile-first prototype: a small business owner chats with an advisor, gets one clear monthly price, completes KYC and
tracks the order. Fictional operator (Accel Business); all data is synthetic. Hackathon project, Enterprise Track A.

Open the app in its own tab: {direct}. On a phone, use "Install app" (Android) or "Add to Home Screen" (iPhone).

Source code: https://github.com/adityamalik24/udyam-digital
"""


def direct_url(user: str, name: str) -> str:
    sub = f"{user}-{name}".lower().replace("_", "-").replace(".", "-")
    return f"https://{sub}.hf.space"


def committed_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    return [f for f in out if f and f.startswith(NEED) and pathlib.Path(f).name not in SKIP_NAMES and "__pycache__" not in f]


def main() -> None:
    load_dotenv(ROOT / ".env")
    need = {k: os.environ.get(k, "").strip() for k in ("HF_TOKEN", "LLM_API_KEY", "SPACE_PARTNER_PASSCODE")}
    missing = [k for k, v in need.items() if not v]
    if missing: sys.exit(f"Add these to .env first: {', '.join(missing)}")
    if len(need["SPACE_PARTNER_PASSCODE"]) < 8: sys.exit("SPACE_PARTNER_PASSCODE should be at least 8 characters.")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *NEED], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty: sys.exit("Commit your changes first: the Space gets the committed version.\n" + dirty)

    name = sys.argv[1] if len(sys.argv) > 1 else "udyam-digital"
    api = HfApi(token=need["HF_TOKEN"])
    user = api.whoami()["name"]
    repo = f"{user}/{name}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    # Settings first, so the first build already has them.
    api.add_space_secret(repo, "LLM_API_KEY", need["LLM_API_KEY"])
    api.add_space_secret(repo, "PARTNER_PASSCODE", need["SPACE_PARTNER_PASSCODE"])
    api.add_space_variable(repo, "AB_TEST", "off")
    api.add_space_variable(repo, "FRAME_ANCESTORS", "https://huggingface.co")

    with tempfile.TemporaryDirectory() as tmp:
        for f in committed_files():
            dst = pathlib.Path(tmp, f); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / f, dst)
        pathlib.Path(tmp, "README.md").write_text(README.format(direct=direct_url(user, name)), encoding="utf-8")
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        api.upload_folder(folder_path=tmp, repo_id=repo, repo_type="space", commit_message=f"Deploy {head}", delete_patterns=["*"])
    print(f"Space:  https://huggingface.co/spaces/{repo}")
    print(f"App:    {direct_url(user, name)}   (share this one; it opens full-screen and installs on phones)")
    print("The first build takes a few minutes. Watch it under the Space's 'Logs' tab.")


if __name__ == "__main__":
    main()
