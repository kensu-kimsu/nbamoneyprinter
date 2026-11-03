"""Conservative, auditable paper-only NBA moneyline selector.

No real wagering, no synthetic odds, no backdated bets.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "paper_betting/ledger.csv"
PRED_DIR = ROOT / "research/live_predictions"
ODDS_DIR = ROOT / "research/odds_snapshots"
HEADERS = ["bet_id","game_id","game_time_utc","home_team","away_team","market",
           "selection","line","bookmaker","decimal_odds","model_probability",
           "stake_aud","placed_at_utc","status","result","profit_aud","bankroll_aud"]


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(dt.timezone.utc)


def norm(value):
    return " ".join(str(value).lower().replace("la clippers","los angeles clippers").split())


def bankroll(rows):
    return round(100 + sum(float(r["profit_aud"]) for r in rows if r["status"] == "settled" and r["profit_aud"]), 2)


def select(predictions, odds, existing, now, min_edge=0.05):
    existing_games = {r["game_id"] for r in existing}
    balance = bankroll(existing)
    open_exposure = sum(float(r["stake_aud"]) for r in existing if r["status"] == "open")
    exposure_limit = round(balance * 0.05, 2)
    remaining = max(0, round(exposure_limit - open_exposure, 2))
    matches, rejected = [], {"no_matching_market":0,"expired":0,"duplicate":0,"insufficient_edge":0,"stale":0}
    for pred in predictions:
        if pred["game_id"] in existing_games:
            rejected["duplicate"] += 1
            continue
        tip = timestamp(pred["game_time_utc"])
        if tip <= now:
            rejected["expired"] += 1
            continue
        candidates = []
        for snap in odds:
            captured = timestamp(snap["captured_at_utc"])
            if captured > now or (now-captured).total_seconds() > 3600 * 6:
                continue
            for line in snap["payload"]["data"]:
                if line.get("market") != "NBA_H2H":
                    continue
                if abs((timestamp(line["game_start_iso"])-tip).total_seconds()) > 60:
                    continue
                if norm(line.get("player_or_team")) != norm(pred["home_team"]) or norm(line.get("away_team")) != norm(pred["away_team"]):
                    continue
                for book, price in line.get("prices", {}).items():
                    if not isinstance(price, dict):
                        continue
                    scraped = timestamp(price.get("scraped_at",snap["captured_at_utc"]))
                    if scraped > now or (now-scraped).total_seconds() > 3600 * 6:
                        continue
                    # HaterPicks H2H 'over'/'under' side mapping is not documented.
                    # Do not assume 'over' means home and risk invalid selections.
                    candidates.append((book, price, captured))
        if not candidates:
            rejected["no_matching_market"] += 1
            continue
        # Block until the feed provides verified home/away moneyline side semantics.
        rejected["no_matching_market"] += 1
    return matches, {"bankroll_aud":balance,"available_exposure_aud":remaining,"rejected":rejected,
                     "reason":"No verified HaterPicks H2H home/away side mapping. No bets can be placed safely."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--predictions",help="Prediction JSON; defaults to latest saved file")
    p.add_argument("--odds",help="Odds snapshot JSON; defaults to latest saved file")
    args=p.parse_args()
    pred_path=pathlib.Path(args.predictions) if args.predictions else max(PRED_DIR.glob("predictions-*.json"))
    odds_path=pathlib.Path(args.odds) if args.odds else max(ODDS_DIR.glob("nba-odds-*.json"))
    predictions=json.loads(pred_path.read_text())["predictions"]
    odds=[json.loads(odds_path.read_text())]
    with LEDGER.open(newline="") as f:
        existing=list(csv.DictReader(f))
    bets, report=select(predictions,odds,existing,dt.datetime.now(dt.timezone.utc))
    report.update({"predictions_checked":len(predictions),"eligible_bets":len(bets),
                   "predictions_file":pred_path.name,"odds_file":odds_path.name,
                   "paper_bets_created":0})
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
