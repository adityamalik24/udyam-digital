# Udyam Digital

Mobile-first journey for small businesses: chat with an advisor, get one clear monthly price, complete KYC, track the order. Fictional operator (Accel Business); all data is synthetic. YTL Hackathon 2026, Enterprise Track A.

## Run
```
brew install tesseract          # Linux: apt install tesseract-ocr
pip install -r requirements.txt
uvicorn web.server:app --port 8000
pytest -q
python tests/run_scenarios.py
```
Open http://localhost:8000 on a phone-width window. The staff view (Partner queue) is at http://localhost:8000/partner, or use the "Staff view" link in the footer.

Set `LLM_API_KEY` (free Gemini key) in `.env` to enable LLM extraction, rewording, translation and voice input. It can hit free-tier limits, in which case the app falls back to the parser and shows a notice. Without it the advisor is fully functional on its deterministic parser, in English, Hindi and Hinglish; only voice input and translating earlier replies need the key.

| Setting | Default | What it does |
|---|---|---|
| `LLM_API_KEY` | unset | Gemini key, as above |
| `PARTNER_PASSCODE` | unset | Locks `/partner` and its API behind a staff passcode (10 wrong tries a minute at most). Unset, the staff view is open, which is only fine on your own computer |
| `AB_TEST` | `on` | `off` shows every visitor the same quote layout (A), for a demo or judging |
| `UDYAM_DB` | `udyam.db` | Where the SQLite file lives. Delete it, with the server stopped, for a clean start |

## Web front end (the main app)
`web/` is the product: a FastAPI JSON API over `core/`, and a plain-JavaScript mobile site with voice input. The `Dockerfile` packages it for any Docker host: tested at 512 MB and 0.1 CPU, where it fits in memory but a 4-document KYC check takes 1–2 minutes.

The older Streamlit front end (`streamlit run app/Home.py`) runs on the same `core/` and is frozen as of 7 Nov 2026.

## Team and data features
| Feature | Where | What it shows |
|---|---|---|
| Live dashboard | Partner queue → Live dashboard | The funnel from this app's own events (a random id and a step, never a person), the deck's metrics against their targets, the "keep at zero" guardrails, how AI replies were made, and hand-offs by reason |
| A/B test | Quote page, read on the dashboard | Half of visitors also see "about ₹N a day" under the monthly price; acceptance is compared with a two-proportion test, and no winner is called below about 100 per variant |
| Businesses like yours | Quote and Tracker | For lines already in the plan, the share of past customers in the segment who had them (never an upsell), and the old field process's activation time as a yardstick |
| Maker-checker KYC review | Partner queue → KYC review | One person proposes, a different person confirms, and only then does the owner's result change. Reversed rejections are counted as false rejections |
| File signals | Partner queue → KYC review | Editing software in a file's metadata, or a PDF changed after it was first saved (signed PDFs excepted). For reviewers only: they never change a verdict |
| Snap your bill | Quote → Compare with your current bill | Local OCR reads the amount due; the owner sees it and can change it, and the photo is dropped |
| Find my order | Tracker (no order yet) | Reopen an order from another day or phone: order number, the mobile given on the Consent page, then a one-time code (shown on screen in this demo; a real launch sends it by SMS). Rate-limited, and the code expires after 5 minutes or 3 wrong tries |
| Evidence | Partner queue → Evidence | Reruns all four advisor scenario sets and the security probes on this computer, each in its own process with a throwaway database and no AI key, next to the KYC self-check |
| Security probes | `python tests/red_team.py` (also in `pytest`) | 32 scripted attacks: price tampering, other people's orders, forged requests, oversized or fake uploads, path traversal, script and SQL injection, ID numbers in chat, session fixation, malformed codes, the staff lock and code guessing |
| Accessibility | `python tests/a11y_check.py` (axe-core, WCAG 2.1 A and AA) | 19 page states, including errors and results that only appear after an action: 0 violations. Needs `pip install playwright axe-playwright-python` |
| Regional-language chat | Advisor, with Gemini on | Messages in Bengali, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Tamil or Telugu get replies in that language when Gemini can translate them, with prices and names protected; otherwise in English. The screens are in English and Hindi |
| Staff view link | Footer of every page | "Staff view" on customer pages and "Customer app" on the staff view, for demos. Set `PARTNER_PASSCODE` if anyone else uses the laptop |
| Read aloud | Advisor | The phone's own voices read the latest reply, in the script it's written in |
| Routing, churn watchlist, call-first reasons | Partner queue → Leads and routing | Field visits only for site surveys (the data shows they cost several times more per activation elsewhere), paid orders ranked by churn risk from how often the owner had to chase us, and the top reasons plus an opening line for each dropped lead |
| Payback what-if | Partner queue → Payback what-if | Starts from the deck's figures (micro: ₹20,007 ÷ ₹2,505 ≈ 8 months) and shows the effect of moving sales to phone and app, prices, or churn |
| Data rights | Your Data page | Download everything as JSON, ask for a correction, or erase; plus a Kantara-format JSON consent receipt and a [breach runbook](docs/breach_runbook.md) |
| CI | `.github/workflows/tests.yml` | Every push runs all tests and scenario sets with no API key |

## Voice input
The Advisor's microphone records in the browser, converts to 16 kHz WAV, and sends it to Gemini to be written down in the language and script spoken. The words land in the chat box for the owner to check: nothing is sent by itself, because a misheard number would change the plan. It has its own unticked consent, since audio can't be redacted before it leaves; the recording is never stored, and the transcript is redacted like typed text.

## Advisor testing
`python tests/run_scenarios.py [file]` runs a scenario set: `advisor_scenarios.yaml` (regressions), `advisor_dev.yaml` and `advisor_unseen.yaml` (new wording).
Without the LLM, first-run scores were 7/28 on the dev set and 22/30 on the unseen set, which was written after the first round of fixes. All sets pass now, but they have since been used for fixing, so they no longer measure unseen wording. None of this is the judges' scenario pack.
Regional scripts get an honest reply: the chat continues in English or Hindi, or passes to a specialist.

## Call-back requests
The Advisor page has a "Talk to a person" form, opened automatically after a hand-off. Streamlit Cloud can reset the SQLite file on restart, so production needs a hosted database and a signed-in staff view.

## Partner queue
Stretch goal: `Partner queue` lists advisor hand-offs and ranks leads lost to our process, using a model fed only what is known when a lead arrives.

## Decisions worth checking
| Decision | Why |
|---|---|
| Price = midpoint of the catalogue range | Activated leads average 0.48 of the range, with no difference by tier or segment |
| Tier 3 gets no plan, and a hand-off | Every catalogue product is sold in Tier 1 and 2 only |
| Single-site micro businesses get AirFiber first | Cheapest eligible link. Catalogue describes it as "for sites without fibre", so Fibre 100 is a ₹100 upgrade when fibre is wanted |
| First payment = first month + setup | Our assumption; the data doesn't give billing terms |
| Email at ₹138 per user | The ₹137.50 midpoint rounds up, so 6 users show ₹828, ₹3 above the exact midpoint |
| Quote valid 15 days | Our assumption; the data doesn't specify one |
| Udyam date and activity are not checked | They disagree with the registry for nearly all applicants including clean ones, so they look like generator noise |
| Missing Udyam certificate = needs_review | The brief lists it as a required KYC document |
| `rejected` needs hard evidence | An inactive registration, or the same non-look-alike GSTIN substitution in every read of a straight, good-resolution image. A tilted, small or noisy image goes to a person instead, so a poor photo can't get a clean applicant rejected |
| A read can only confirm a GSTIN character at full length, and can't outvote a majority on a good image | Both rules exist because a stress test let forgeries through without them |
| Messages never show a registry value | A forger shouldn't learn from our reply what the document should say. Stored reasons also hold no names or numbers |
| Every printed GST field is compared with the registry | All 12 applicants agree on them apart from the planted problems, so this adds no false alarms and catches an edited trade name, address, business type or date |
| No record of the signatory means needs_review | When there's nothing to compare the name with, we don't vouch for it. No specimen hits this |
| Tracker dates are shown on the demo's today, in IST | Eligibility and estimates use 2026-07-15, so real timestamps would read months apart. Stored times stay real, and consent records show their real time |
| Reschedule from the catalogue's install time, up to 60 days ahead | An earlier date would promise something the data doesn't support. 60 days is our assumption |
| No activation date, no refund promise | The data gives neither, and rule 10 forbids promises the rules don't support |
| Number lookup shows only a status | Enough to catch a cancelled GSTIN before any upload, without letting anyone read other businesses' details. The typed GSTIN stays in the session to compare with the certificate, is dropped after verifying, and is never stored |
| Files are sorted by content, and we don't guess beyond one gap | One unrecognised file with one type missing is that type. Two different documents of one type go to a person, never a silent pick |
| A PDF is drawn and read like a photo | Its hidden text layer can differ from what's printed, so it is never trusted |
| Our price stays the catalogue midpoint, without adding GST | Team RNG's other build adds an assumed 18%. The data doesn't state tax, so the Quote page says plainly that GST isn't confirmed |
| K05 stays `needs_review` | The brief lists the Udyam certificate as required. The other build verifies K05 from the registry. We keep it with a person and tell them the registry has a record, so it's quick to settle |
| Three KYC verdicts only | The project rules ask for `verified`, `needs_review` and `rejected`. The other build's extra retake and confirm states are covered by plain next steps |
| A second connection is never added to hold up an add-on on a leased line | It wouldn't be the smallest plan. The add-on is listed as not included, with the reason |
| Lead score leaves out language | A lead shouldn't rank lower for the language its owner speaks. Accuracy doesn't change (AUC 0.71) |
| Chat uses a notice and an off switch rather than an unticked box | Unlike KYC, owners type this themselves, and a box before the first message would stop them starting. A lawyer should confirm this |
| Gemini reads through a forced tool call, and writes around `{{slots}}` | Learned from Team RNG's other build. The schema constrains what it can return, each value is checked alone, and it can't type a price or product name in any language |
| What code reads directly beats what the model reads | The model only fills gaps and spots intent, so a misreading can't override a stated fact |
| Regional languages run only with Gemini on | Replies are translated around slots, so numbers stay exact. Without Gemini the owner is told plainly to use English or Hindi |
| Streamlit pinned to the tested version | `use_container_width` is due for removal, so an unpinned rebuild could break every page |
| "Clinic wants email" adds a link and Endpoint Security | Our scenario 2. Goes beyond rule 4 (stated needs only): all 138 professional-office customers with email also bought a link, 67 bought security. Saying "we already have internet" removes the link |
| CCTV and similar still add a link when the owner has one | The catalogue requires a listed product in the same bundle, and we can't confirm a link from another provider |
| A typed GSTIN is looked up, then discarded | Only an active registry record counts as having a GSTIN; the number is never stored or repeated |
| Staff, sites and GSTIN are asked only when they change the plan | `question_matters` tries the possible answers against the rules, so a website-only request skips them. The Quote page asks if an add-on needs them |
| Tiers for cities outside the data | The leads cover 22 cities. Other tier 2 and 3 lists are our assumption; unlisted cities are asked, not guessed |

## KYC results (our manual review, not the judges' key)
Verified: K02 (rotated scan), K03, K08, K09, K12. Needs review: K04 (blurred GST), K05 (no Udyam certificate), K07 (legal name "Shri" vs registry "Neelgiri"), K10 (signatory ID differs from the contact on the application; the other 11 applicants match), K11 (bill 257 days old). Rejected: K01 (GSTIN cancelled), K06 (certificate prints 8189, registry 5189).

Docs: [architecture](docs/architecture.md), [demo script](docs/demo_script.md), [privacy note](docs/privacy_note.md), [analysis](notebooks/leads_analysis.ipynb).
