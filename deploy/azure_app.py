"""Publishes the web app to Azure Container Apps (works on an Azure for Students subscription, no card). Run from the
repo root after `az login`:

    .venv/bin/python deploy/azure_app.py [region]        # default region: centralindia

Needs, in .env (gitignored): LLM_API_KEY, and SPACE_PARTNER_PASSCODE (the staff passcode for the public app, 8+ characters;
the name is kept from the Hugging Face attempt). Both go in as Container Apps secrets, never into the image or a file.

What it does, safe to run again (the second run only ships a new version):
  1. registers the Azure services it needs and creates the resource group "udyam-rg";
  2. creates a small container registry and pushes an image built here (linux/amd64, via Docker/OrbStack);
  3. creates or updates the app "udyam-digital": 1 CPU, 2 GB, exactly one copy (sessions live in memory, so one copy is
     required), the staff passcode on and the A/B test off.
It prints the https link at the end.
"""
from __future__ import annotations
import hashlib, json, pathlib, shutil, subprocess, sys
from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parents[1]
GROUP, ENV, APP, IMAGE = "udyam-rg", "udyam-env", "udyam-digital", "udyam-web"


def az(*args: str, check: bool = True, quiet: bool = False) -> str:
    """Runs one az command. Secrets are passed as arguments, never through a shell, and output is never echoed."""
    r = subprocess.run(["az", *args, "--only-show-errors", "-o", "json"], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"az {args[0]} {args[1] if len(args) > 1 else ''} failed:\n{r.stderr.strip()[:1500]}")
    return r.stdout if r.returncode == 0 else ("" if quiet else r.stderr)


def step(text: str) -> None:
    print(f"- {text}", flush=True)


def main() -> None:
    region = sys.argv[1] if len(sys.argv) > 1 else "centralindia"
    env_file = {k: (v or "").strip() for k, v in dotenv_values(ROOT / ".env").items()}
    key, code = env_file.get("LLM_API_KEY", ""), env_file.get("SPACE_PARTNER_PASSCODE", "")
    if not key or len(code) < 8: sys.exit("Add LLM_API_KEY and SPACE_PARTNER_PASSCODE (8+ characters) to .env first.")
    for tool in ("az", "docker"):
        if not shutil.which(tool): sys.exit(f"{tool} isn't installed.")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0: sys.exit("Docker isn't running. Start OrbStack (or Docker Desktop) and try again.")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty: sys.exit("Commit your changes first, so the app online matches the code on GitHub.\n" + dirty)

    account = json.loads(az("account", "show"))
    step(f"Subscription: {account['name']}")
    sub = account["id"]
    registry = "udyam" + hashlib.sha1(sub.encode()).hexdigest()[:10]  # globally unique, the same on every run
    tag = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    step("Registering the Azure services this needs (first run only takes a minute or two)")
    for ns in ("Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry"):
        az("provider", "register", "--namespace", ns, "--wait")
    az("extension", "add", "--name", "containerapp", "--upgrade", "--yes", check=False)  # built in on newer az versions

    step(f"Resource group {GROUP} in {region}")
    az("group", "create", "--name", GROUP, "--location", region)

    step(f"Container registry {registry}")
    if not az("acr", "show", "--name", registry, "--resource-group", GROUP, check=False, quiet=True):
        az("acr", "create", "--name", registry, "--resource-group", GROUP, "--sku", "Basic", "--admin-enabled", "true", "--location", region)
    server = json.loads(az("acr", "show", "--name", registry, "--resource-group", GROUP))["loginServer"]
    creds = json.loads(az("acr", "credential", "show", "--name", registry))
    user, password = creds["username"], creds["passwords"][0]["value"]

    image = f"{server}/{IMAGE}:{tag}"
    step(f"Building and pushing {IMAGE}:{tag} (linux/amd64; the first build takes several minutes)")
    login = subprocess.run(["docker", "login", server, "--username", user, "--password-stdin"], input=password, capture_output=True, text=True)
    if login.returncode != 0: sys.exit("docker login to the registry failed:\n" + login.stderr[:800])
    build = subprocess.run(["docker", "buildx", "build", "--platform", "linux/amd64", "-t", image, "--push", "."], cwd=ROOT)
    if build.returncode != 0: sys.exit("The image build or push failed (see above).")

    step(f"Container Apps environment {ENV}")
    if not az("containerapp", "env", "show", "--name", ENV, "--resource-group", GROUP, check=False, quiet=True):
        az("containerapp", "env", "create", "--name", ENV, "--resource-group", GROUP, "--location", region)

    secrets = [f"llm-api-key={key}", f"partner-passcode={code}"]  # the registry password is stored by --registry-password itself
    env_vars = ["LLM_API_KEY=secretref:llm-api-key", "PARTNER_PASSCODE=secretref:partner-passcode", "AB_TEST=off"]
    exists = az("containerapp", "show", "--name", APP, "--resource-group", GROUP, check=False, quiet=True)
    if not exists:
        step(f"Creating the app {APP}")
        az("containerapp", "create", "--name", APP, "--resource-group", GROUP, "--environment", ENV, "--image", image,
           "--registry-server", server, "--registry-username", user, "--registry-password", password,
           "--target-port", "10000", "--ingress", "external", "--cpu", "1.0", "--memory", "2.0Gi",
           "--min-replicas", "1", "--max-replicas", "1", "--secrets", *secrets, "--env-vars", *env_vars)
    else:
        step(f"Updating the app {APP}")
        az("containerapp", "secret", "set", "--name", APP, "--resource-group", GROUP, "--secrets", *secrets)
        az("containerapp", "update", "--name", APP, "--resource-group", GROUP, "--image", image,
           "--cpu", "1.0", "--memory", "2.0Gi", "--min-replicas", "1", "--max-replicas", "1", "--set-env-vars", *env_vars)

    fqdn = json.loads(az("containerapp", "show", "--name", APP, "--resource-group", GROUP))["properties"]["configuration"]["ingress"]["fqdn"]
    print(f"\nApp:        https://{fqdn}\nStaff view: https://{fqdn}/partner  (passcode from .env)\n"
          "It can take a minute after this for the new version to answer.", flush=True)


if __name__ == "__main__":
    main()
