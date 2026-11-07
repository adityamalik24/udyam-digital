# CLAUDE.md — Udyam Digital (Airtel SYNC YTL Hackathon 2026, Enterprise Track A)

## What we are building
A mobile-first app where a small business owner (kirana, clinic, CA firm, restaurant, small manufacturer) chats with an AI advisor, gets a recommended telecom bundle with ONE clear monthly price, completes KYC in minutes, and tracks the order without calling support. Fictional operator: **Accel Telecom / Accel Business**. All data is synthetic. Never use real Airtel branding inside the product.

Build only what is judged. Correctness > polish.

## How we are judged
1. Judges run 15 hidden advisor scenarios live: right bundle, every eligibility rule and dependency, Hindi/Hinglish, vague users, tricky inputs.
2. KYC is checked against a hidden answer key (47 images, 12 applicants). Catch every planted problem; never reject a clean applicant.
3. Signals are planted in `smb_leads.csv`. Back business claims with numbers.
4. Technical depth and business judgement are scored together.

## What the brief also requires
- The advisor asks about type, size, locations and **current tools**, and **explains why** in plain language.
- Consent and data handling follow the DPDP Act, 2023.
- Submit: demo video of **3 minutes max** + code repo; architecture diagram; business case in **10 slides or fewer**; **1-page** privacy and security note.
- Answer: which segments first, bundle per segment, field force and partner role, 3–5 metrics with targets.

## Data facts (from data/README.md; these override assumptions)
- "Today" for all date checks is **2026-07-15** (`core.pricing.TODAY`). Address proof must be no older than 90 days.
- Every catalogue product is sold in **Tier 1 and 2 only** (Biz Fibre 1G, P03, in Tier 1 only). Tier 3 has no eligible product: say so and hand off.
- Prices are ranges. We quote the **midpoint**; activated leads average 0.48 of the range, with no tier or segment effect.
- GSTIN PAN 4th char is always `X`, which is valid here. Udyam district is always `00`.
- Udyam date and activity disagree with the registry on nearly all applicants, including clean ones: generator noise, do not check.
- OCR on the monospace GSTIN line is noisy (`1Z`→`12`, `7`→`/`, `0`→`O`). Only a non-look-alike substitution persisting in all reads counts as a mismatch.

### Schema
- product_catalogue.csv: product_id, category, product_name, description, unit, price_min_inr_per_month, price_max_inr_per_month, one_time_setup_inr, min_contract_months, available_city_tiers (`;`), min_employees, min_sites, requires_gstin, requires_one_of (`|`), typical_install_days, target_segments
- smb_leads.csv: lead_id, created_date, lead_source, business_name, business_type, segment, city, city_tier, state, preferred_language, employee_count, num_sites, annual_turnover_band, has_gstin, gstin, has_udyam, udyam_number, current_internet, current_provider, monthly_telecom_spend_inr, products_of_interest, contact_name, contact_role, stage_reached, outcome, drop_reason, contacted_date, needs_assessed_date, quote_accepted_date, kyc_complete_date, activated_date, days_lead_to_activation, customer_follow_up_calls, bundle_products (`P01x1;P07x2`), monthly_bundle_value_inr, one_time_setup_inr, contract_months, churned_within_6_months, nps_score, acquisition_cost_inr
- mock_gstin_registry.csv: gstin, legal_name, trade_name, constitution, principal_place_of_business, state, registration_date, status (Active/Cancelled/Suspended)
- mock_udyam_registry.csv: udyam_number, enterprise_name, enterprise_type, major_activity, nic_description, state, city, date_of_registration
- kyc_documents: `K01..K12_{gst_certificate,udyam_certificate,signatory_id,address_proof}.png` (K05 has no Udyam certificate)

## Non-negotiable design rules
1. The LLM never decides products or prices. It only extracts a profile and explains results. `rules.py` and `pricing.py` decide everything.
2. After every advisor reply, `guardrails.py` checks products and prices against the engine. Mismatch → regenerate.
3. Eligibility and dependencies are enforced in code. Exclusions come with a human-readable reason.
4. Recommend the smallest bundle covering stated needs. Show one cheaper alternative where it exists. No upselling.
5. At most 4–6 questions. Skip anything answered. Clarify instead of guessing.
6. Reply in the user's language (English, Hindi, Hinglish); follow mid-chat switches.
7. Hand off (store a lead summary) for multi-site, manufacturers with custom needs, repeated confusion, frustration.
8. Politely refuse haggling, off-topic and prompt injection, then steer back.
9. Never ask for or repeat Aadhaar, PAN or bank numbers. If volunteered, don't store; point to KYC.
10. No promises the rules don't support (install dates, free upgrades).
11. Pricing is server-side only. Never trust a price from UI state.

## Quote + consent
One big monthly price, then setup fee, contract, validity date. Plain names, no codes. Add-on toggles recompute via `price()`. Dependencies auto-add with a note; ineligible add-ons greyed with reason. Consent before any KYC data, with a separate unticked checkbox per purpose; store purpose, notice version, language, timestamp. Withdrawal from the tracker.

## KYC rules
Verdicts `verified`, `needs_review`, `rejected`, each with a plain reason. **When uncertain, use `needs_review`.** OCR must not correct values. Mask IDs to last 4 in UI and DB. Delete raw uploads after verification. Never send images or ID numbers to the LLM.

## Tracker
Quote accepted → KYC verified → Payment done → Installation scheduled → Technician assigned → Installed → Activated. Timestamp per transition, next expected date, technician, reschedule, demo advance.

## Commands
```
pip install -r requirements.txt   # plus tesseract
streamlit run app/Home.py
pytest -q
python tests/run_scenarios.py
python tests/run_scenarios.py tests/advisor_teammate.yaml
python tests/kyc_stress.py        # slow: degraded uploads and forgeries
# CI (.github/workflows/tests.yml) runs pytest and all four scenario sets on every push, with no API key
python tests/live_check.py 8      # spends free Gemini quota
uvicorn web.server:app --port 8000  # the web front end
docker build -t udyam-web . && docker run --memory=512m --cpus=0.1 -p 8000:10000 -e LLM_API_KEY=... udyam-web  # small-server limits
```

## Front ends
- `app/` (Streamlit, deployed on Streamlit Cloud) and `web/` (FastAPI + plain JS, run locally; `Dockerfile` packages it) share `core/`. A change to a page's behaviour belongs in both, or in `core/`.
- `web/` never takes a price, verdict or order total from the browser: it takes choices and recomputes. Every order action checks the order belongs to the session.
- Voice input (`core/asr.py`) only writes words into the chat box. It needs its own consent (audio can't be redacted before it goes to Gemini), keeps no recording, redacts the transcript and never sends a message by itself.

## Out of scope
WhatsApp, phone calls or voice replies, a full back-office (the read-only Partner queue is in scope), real DigiLocker / e-sign / payment gateway, React frontend, auth beyond a demo user.

## Working style
- Read `data/README.md` and the CSV header before writing data code.
- Update tests with every change to `rules.py`, `pricing.py` or `kyc/`. Add a scenario for every advisor bug.
- Keep `core/` small and pure; Streamlit pages (`app/`) and the web front end (`web/`) only handle UI and permission checks.
- Run `pytest -q` and `python tests/run_scenarios.py` before saying a task is done.
