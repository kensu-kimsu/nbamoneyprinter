"""Audit NBA slate completeness and exact HaterPicks game-line coverage.

The schedule is fetched independently from ESPN, not inferred from predictions.
A green audit does not imply bets are eligible: unmatched odds remain no-bet.
"""
import argparse
import datetime as dt
import json
import pathlib
from research.espn_baseline import fetch_day, parse_game

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRED=ROOT/"research/live_predictions"
ODDS=ROOT/"research/odds_snapshots"
REPORT=ROOT/"research/schedule_audits"


def utc(value):
    return dt.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(dt.timezone.utc)


def team(value):
    return " ".join(str(value).lower().replace("la clippers","los angeles clippers").split())


def audit(predictions, snapshots, scheduled, now):
    predicted={str(p["game_id"]):p for p in predictions}
    future={g["game_id"]:g for g in scheduled if g["state"]=="pre" and g["tipoff_utc"]>now}
    # ESPN's date-based endpoint uses UTC schedule dates; do not infer a full slate
    # from one call or from bookmaker rows.
    missing=sorted(set(future)-set(predicted))
    extra=sorted(set(predicted)-set(future))
    matched=[]
    unmatched=[]
    for game_id,g in future.items():
        p=predicted.get(game_id)
        if not p:
            continue
        valid=[]
        for snap in snapshots:
            captured=utc(snap["captured_at_utc"])
            if captured>now or (now-captured).total_seconds()>21600:
                continue
            for row in snap["payload"]["data"]:
                if row.get("market")!="NBA_H2H":
                    continue
                if abs((utc(row["game_start_iso"])-g["tipoff_utc"]).total_seconds())>60:
                    continue
                if team(row.get("player_or_team"))!=team(g["home"]) or team(row.get("away_team"))!=team(g["away"]):
                    continue
                for book,price in row.get("prices",{}).items():
                    if not isinstance(price,dict):
                        continue
                    scraped=utc(price.get("scraped_at",snap["captured_at_utc"]))
                    if scraped<=now and (now-scraped).total_seconds()<=21600:
                        valid.append({"bookmaker":book,"market_id":row["id"],"scraped_at":scraped.isoformat()})
        item={"game_id":game_id,"home":g["home"],"away":g["away"],"tipoff_utc":g["tipoff_utc"].isoformat()}
        if valid:
            item["markets"]=valid
            matched.append(item)
        else:
            unmatched.append(item)
    return {"audited_at_utc":now.isoformat(),"scheduled_future_games":len(future),
            "predicted_future_games":len(set(predicted)&set(future)),
            "missing_predictions":missing,"predictions_not_on_future_slate":extra,
            "matched_h2h_games":matched,"missing_or_stale_h2h_odds":unmatched,
            "complete_prediction_coverage":not missing and not extra,
            "complete_odds_coverage":not unmatched,
            "note":"H2H over/under side mapping is unverified; matched market does not authorize a bet."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",help="NBA US Eastern calendar date YYYY-MM-DD; defaults to next slate")
    args=parser.parse_args()
    now=dt.datetime.now(dt.timezone.utc)
    pred_path=max(PRED.glob("predictions-*.json"))
    predictions=json.loads(pred_path.read_text())["predictions"]
    # Pull the entire relevant UTC date range, including adjacent days.
    if args.date:
        from zoneinfo import ZoneInfo
        local=dt.datetime.fromisoformat(args.date).replace(tzinfo=ZoneInfo("America/New_York"))
        start=local.astimezone(dt.timezone.utc)
        end=(local+dt.timedelta(days=1)).astimezone(dt.timezone.utc)
    else:
        future_times=sorted(utc(p["game_time_utc"]) for p in predictions if utc(p["game_time_utc"])>now)
        if not future_times:
            raise RuntimeError("No future predictions to audit")
        from zoneinfo import ZoneInfo
        eastern=ZoneInfo("America/New_York")
        first_day=future_times[0].astimezone(eastern).date()
        local=dt.datetime.combine(first_day,dt.time.min,tzinfo=eastern)
        start=local.astimezone(dt.timezone.utc)
        end=(local+dt.timedelta(days=1)).astimezone(dt.timezone.utc)
    days=[(start+dt.timedelta(days=i)).date() for i in range(-1,4)]
    games={}
    for day in days:
        for raw in fetch_day(day):
            game=parse_game(raw)
            if start<=game["tipoff_utc"]<end:
                games[game["game_id"]]=game
    if not games:
        raise RuntimeError("Schedule provider returned no games for audit window")
    snapshots=[json.loads(p.read_text()) for p in sorted(ODDS.glob("nba-odds-*.json"))[-5:]]
    report=audit(predictions,snapshots,list(games.values()),now)
    report["prediction_file"]=pred_path.name
    REPORT.mkdir(parents=True,exist_ok=True)
    target=REPORT/("audit-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
    target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    print("SAVED",target.relative_to(ROOT))
    if not report["complete_prediction_coverage"]:
        raise SystemExit("Prediction coverage incomplete; no bets allowed")


if __name__=="__main__":
    main()
