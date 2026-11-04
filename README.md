# Udyam Digital

Mobile-first journey for small businesses: chat with an advisor, get one clear monthly price, complete KYC, track the order. Fictional operator (Accel Business); all data is synthetic. YTL Hackathon 2026, Enterprise Track A.

## Run
```
brew install tesseract          # Linux: apt install tesseract-ocr (packages.txt covers Streamlit Cloud)
pip install -r requirements.txt
streamlit run app/Home.py
pytest -q
python tests/run_scenarios.py
```
Set `LLM_API_KEY` to enable LLM extraction and rewording. Without it the advisor is fully functional on its deterministic parser, in English, Hindi and Hinglish.
Deploy on Streamlit Community Cloud with `app/Home.py` as the entrypoint and the key in app secrets.

## Advisor testing
`python tests/run_scenarios.py [file]` runs a scenario set: `advisor_scenarios.yaml` (regressions), `advisor_dev.yaml` and `advisor_unseen.yaml` (new wording).
Without the LLM, first-run scores were 7/28 on the dev set and 22/30 on the unseen set, which was written after the first round of fixes. All sets pass now, but they have since been used for fixing, so they no longer measure unseen wording. None of this is the judges' scenario pack.
Regional scripts get an honest reply: the chat continues in English or Hindi, or passes to a specialist.

## Decisions worth checking
| Decision | Why |
|---|---|
| Price = midpoint of the catalogue range | Activated leads average 0.48 of the range, with no difference by tier or segment |
| Tier 3 gets no plan, and a hand-off | Every catalogue product is sold in Tier 1 and 2 only |
| Single-site micro businesses get AirFiber first | Cheapest eligible link. Catalogue describes it as "for sites without fibre", so Fibre 100 is a ₹100 upgrade when fibre is wanted |
| Quote valid 15 days | Our assumption; the data doesn't specify one |
| Udyam date and activity are not checked | They disagree with the registry for nearly all applicants including clean ones, so they look like generator noise |
| Missing Udyam certificate = needs_review | The brief lists it as a required KYC document |

## KYC results (our manual review, not the judges' key)
Verified: K02 (rotated scan), K03, K08, K09, K10, K12. Needs review: K04 (blurred GST), K05 (no Udyam certificate), K07 (legal name "Shri" vs registry "Neelgiri"), K11 (bill 257 days old). Rejected: K01 (GSTIN cancelled), K06 (certificate prints 8189, registry 5189).

Docs: [architecture](docs/architecture.md), [demo script](docs/demo_script.md), [privacy note](docs/privacy_note.md), [analysis](notebooks/leads_analysis.ipynb).
