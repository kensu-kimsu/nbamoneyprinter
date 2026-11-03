"""Generate auditable pregame NBA moneyline predictions from existing XGBoost model.

Input is a JSON list of pregame feature rows and verified market metadata.
This module does NOT invent feature data or scrape stale seasons.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib

import numpy as np
import xgboost as xgb

from research.history import record_prediction, parse_utc

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "Models" / "XGBoost_Models"


def find_model():
    models = sorted(MODEL_DIR.glob("*ML*.json"))
    if not models:
        raise RuntimeError("No moneyline XGBoost model found")
    # Deterministic selection, unlike mtime which can change on Git checkout.
    return models[-1]


def generate(rows, model_path=None, now=None, save=False):
    if not rows:
        raise ValueError("No games supplied")
    model_path = pathlib.Path(model_path) if model_path else find_model()
    booster = xgb.Booster()
    booster.load_model(str(model_path))
    feature_count = booster.num_features()
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.utcoffset() != dt.timedelta(0):
        raise ValueError("Prediction timestamp must be UTC")
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()[:16]
    required = ("game_id", "game_time_utc", "home_team", "away_team",
                "bookmaker", "odds_source", "home_decimal_odds",
                "away_decimal_odds", "features", "feature_source")
    for row in rows:
        for key in required:
            if key not in row or row[key] in (None, ""):
                raise ValueError(f"Missing {key}")
        if parse_utc(row["game_time_utc"]) <= now:
            raise ValueError("Cannot predict a game that already started")
        if len(row["features"]) != feature_count:
            raise ValueError(f"Expected {feature_count} model features, got {len(row['features'])}")
        if any(float(v) != float(v) or abs(float(v)) == float("inf") for v in row["features"]):
            raise ValueError("Features must be finite numbers")
        for key in ("home_decimal_odds", "away_decimal_odds"):
            if float(row[key]) <= 1:
                raise ValueError("Invalid decimal odds")
    features = np.asarray([r["features"] for r in rows], dtype=float)
    output = booster.predict(xgb.DMatrix(features))
    if output.ndim != 2 or output.shape != (len(rows), 2):
        raise ValueError("Unexpected model output shape; expected [away, home] probabilities")
    predictions = []
    for row, probabilities in zip(rows, output):
        if not np.isfinite(probabilities).all() or not np.isclose(sum(probabilities), 1, atol=0.02):
            raise ValueError("Invalid model probabilities")
        for idx, side in ((0, "away"), (1, "home")):
            selection = row[f"{side}_team"]
            odds = float(row[f"{side}_decimal_odds"])
            p = float(probabilities[idx])
            record = {
                "prediction_id": f"{row['game_id']}:{side}:{model_hash}:{now.strftime('%Y%m%dT%H%M%SZ')}",
                "game_id": row["game_id"],
                "game_time_utc": row["game_time_utc"],
                "predicted_at_utc": now.isoformat(),
                "model_version": f"xgb-ml-sha256-{model_hash}",
                "market": "NBA_H2H",
                "selection": selection,
                "model_probability": p,
                "odds_source": row["odds_source"],
                "decimal_odds": odds,
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "bookmaker": row["bookmaker"],
                "feature_source": row["feature_source"],
                "expected_value_per_unit": p * odds - 1,
                "paper_bet": False,
            }
            predictions.append(record)
    if save:
        for prediction in predictions:
            record_prediction(prediction)
    return predictions


def main():
    parser = argparse.ArgumentParser(description="Predict NBA moneylines using verified pregame feature input")
    parser.add_argument("--input", required=True, help="JSON file containing list of game feature rows")
    parser.add_argument("--model", help="Explicit model path; default deterministic ML model")
    parser.add_argument("--save", action="store_true", help="Append predictions to permanent research history")
    args = parser.parse_args()
    rows = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    print(json.dumps(generate(rows, args.model, save=args.save), indent=2))


if __name__ == "__main__":
    main()
