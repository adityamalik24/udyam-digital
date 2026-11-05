"""Where the owner is in the journey, worked out only from real records so the progress bar can't overstate it."""
from .orders import STAGES

STEPS = ("quote", "consent", "kyc", "payment", "tracker")
DONE, TODO, ATTENTION = "done", "todo", "attention"


def progress(order: dict | None, kyc_consent: bool, kyc_verdict: str | None) -> dict[str, str]:
    """Each step is judged on its own, because the owner can move between the pages in any order."""
    stage = order["stage_index"] if order else -1
    kyc = DONE if kyc_verdict == "verified" else ATTENTION if kyc_verdict else TODO
    return {"quote": DONE if order else TODO,
            "consent": DONE if kyc_consent else TODO,
            "kyc": kyc,
            "payment": DONE if stage >= STAGES.index("Payment done") else TODO,
            "tracker": DONE if stage == len(STAGES) - 1 else TODO}


def current(page: str, state: dict[str, str]) -> str:
    """Payment has no page of its own: its button is on the KYC page once KYC is verified."""
    ready_to_pay = state["kyc"] == DONE and state["quote"] == DONE and state["payment"] == TODO
    return "payment" if page == "kyc" and ready_to_pay else page
