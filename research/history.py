"""Append-only, auditable NBA prediction and settlement events.

No prediction is created automatically: callers must supply genuine pregame model output.
Settlement is a separate event. History is never used to fabricate model confidence.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HISTORY = ROOT / "research" / "events.jsonl"
REQUIRED_PREDICTION = (
    "prediction_id", "game_id", "game_time_utc", "predicted_at_utc",
    "model_version", "market", "selection", "model_probability",
    "odds_source", "decimal_odds", "home_team", "away_team",
)
REQUIRED_SETTLEMENT = ("prediction_id", "settled_at_utc", "result", "final_home_score", "final_away_score")
RESULTS = {"won", "lost", "push", "void"}


def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a UTC ISO 8601 string")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("Timestamp must include UTC offset/Z")
    return parsed


def load():
    if not HISTORY.exists():
        return []
    with HISTORY.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append(event):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    # Every event carries a content digest; Git history preserves earlier versions.
    event["sha256"] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def record_prediction(data):
    for field in REQUIRED_PREDICTION:
        if field not in data or data[field] in (None, ""):
            raise ValueError(f"Missing {field}")
    when = parse_utc(data["predicted_at_utc"])
    tipoff = parse_utc(data["game_time_utc"])
    if when >= tipoff:
        raise ValueError("Prediction must be timestamped before game tipoff")
    probability = float(data["model_probability"])
    odds = float(data["decimal_odds"])
    if not 0 <= probability <= 1 or odds <= 1:
        raise ValueError("Invalid probability or decimal odds")
    if not data["prediction_id"].strip():
        raise ValueError("Blank prediction ID")
    existing = load()
    if any(e["type"] == "prediction" and e["data"]["prediction_id"] == data["prediction_id"] for e in existing):
        raise ValueError("Prediction ID already recorded; original cannot be overwritten")
    append({"type": "prediction", "data": data})
    return data["prediction_id"]


def settle(data):
    for field in REQUIRED_SETTLEMENT:
        if field not in data or data[field] in (None, ""):
            raise ValueError(f"Missing {field}")
    settled = parse_utc(data["settled_at_utc"])
    if data["result"] not in RESULTS:
        raise ValueError("Invalid settlement result")
    for score in ("final_home_score", "final_away_score"):
        if int(data[score]) < 0:
            raise ValueError("Invalid score")
    events = load()
    predictions = {e["data"]["prediction_id"]: e["data"] for e in events if e["type"] == "prediction"}
    prediction = predictions.get(data["prediction_id"])
    if prediction is None:
        raise ValueError("Cannot settle an unknown prediction")
    if settled <= parse_utc(prediction["game_time_utc"]):
        raise ValueError("Settlement must occur after tipoff")
    if any(e["type"] == "settlement" and e["data"]["prediction_id"] == data["prediction_id"] for e in events):
        raise ValueError("Prediction already settled; corrections require an audited process")
    append({"type": "settlement", "data": data})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["predict", "settle", "summary"])
    parser.add_argument("--file", help="JSON file containing the event fields")
    args = parser.parse_args()
    if args.action == "summary":
        events = load()
        print(json.dumps({
            "predictions": sum(e["type"] == "prediction" for e in events),
            "settlements": sum(e["type"] == "settlement" for e in events),
        }, indent=2))
        return
    if not args.file:
        parser.error("--file is required for predict/settle")
    data = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    if args.action == "predict":
        record_prediction(data)
    else:
        settle(data)
    print("Event appended. Commit research/events.jsonl to GitHub for permanent history.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as exc:
        sys.exit(f"Error: {exc}")
