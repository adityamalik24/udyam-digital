"""Ranks dropped leads once, while the image is built, so the running server never loads pandas or scikit-learn."""
import json
from pathlib import Path


def build() -> dict:
    from core.propensity import score_leads
    df, auc = score_leads()
    rows = [[str(v) for v in row] for row in df.head(25).values.tolist()]
    return {"auc": auc, "rows": rows}


if __name__ == "__main__":
    Path(__file__).with_name("lead_scores.json").write_text(json.dumps(build()))
