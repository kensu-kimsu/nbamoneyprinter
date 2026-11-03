"""Run OddsHarvester for NBA moneyline and audit exact ESPN game matching.

Research-only integration; never silently assumes outcome ordering.
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo
from research.espn_baseline import fetch_day, parse_game

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"research/oddsportal_snapshots"


def normalized(name):
    return " ".join(str(name).lower().replace("la clippers","los angeles clippers").split())


def read_records(path):
    raw=json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw,list):
        return raw
    if isinstance(raw,dict):
        for key in ("data","matches","results"):
            if isinstance(raw.get(key),list):
                return raw[key]
    raise ValueError("Unknown OddsHarvester JSON schema: manual inspection needed")


def inspect(rows):
    keys=sorted({k for row in rows if isinstance(row,dict) for k in row})
    return {"rows":len(rows),"fields":keys,"first_row_field_types":
            {k:type(v).__name__ for k,v in rows[0].items()} if rows else {}}


def run(day):
    OUT.mkdir(parents=True,exist_ok=True)
    filename=OUT/("oddsportal-"+day.strftime("%Y%m%d")+".json")
    command=["oddsharvester","upcoming","-s","basketball","-l","nba",
             "-d",day.strftime("%Y%m%d"),"-m","home_away","--headless",
             "--concurrency","1","--request-delay","2","--timezone","America/New_York",
             "-f","json","-o",str(filename)]
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=540)
    if result.returncode:
        raise RuntimeError("OddsHarvester failed (exit "+str(result.returncode)+"): "+result.stderr[:5000])
    if not filename.is_file():
        raise RuntimeError("OddsHarvester produced no JSON file")
    rows=read_records(filename)
    if not rows:
        raise RuntimeError("OddsHarvester produced zero NBA records")
    eastern=ZoneInfo("America/New_York")
    start=dt.datetime.combine(day,dt.time.min,tzinfo=eastern).astimezone(dt.timezone.utc)
    end=dt.datetime.combine(day+dt.timedelta(days=1),dt.time.min,tzinfo=eastern).astimezone(dt.timezone.utc)
    scheduled={}
    for offset in range(-1,3):
        for raw in fetch_day((start+dt.timedelta(days=offset)).date()):
            g=parse_game(raw)
            if start<=g["tipoff_utc"]<end:
                scheduled[g["game_id"]]=g
    if not scheduled:
        raise RuntimeError("ESPN schedule returned no NBA games for selected day")
    matches=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        home=normalized(row.get("home_team",""))
        away=normalized(row.get("away_team",""))
        # Do not trust name alone if a kickoff timestamp is unavailable.
        raw_time=row.get("match_date") or row.get("kickoff_utc")
        if not raw_time:
            continue
        try:
            tip=dt.datetime.fromisoformat(str(raw_time).replace("Z","+00:00"))
            if tip.tzinfo is None:
                continue
            tip=tip.astimezone(dt.timezone.utc)
        except ValueError:
            continue
        for game in scheduled.values():
            if (home==normalized(game["home"]) and away==normalized(game["away"])
                and abs((tip-game["tipoff_utc"]).total_seconds())<=60):
                matches.append({"game_id":game["game_id"],"home":game["home"],
                                "away":game["away"],"odds_row":row})
                break
    summary={"date_us_eastern":str(day),"scheduled_games":len(scheduled),
             "scraped_records":len(rows),"exact_matches":len(matches),
             "matched_game_ids":sorted({m["game_id"] for m in matches}),
             "unmatched_game_ids":sorted(set(scheduled)-{m["game_id"] for m in matches}),
             "schema":inspect(rows),
             "paper_bets_enabled":False,
             "reason":"Bookmaker outcome mapping and model calibration not yet validated"}
    report=OUT/("audit-"+day.strftime("%Y%m%d")+".json")
    report.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--date",help="US Eastern NBA slate date YYYY-MM-DD")
    args=p.parse_args()
    day=dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(ZoneInfo("America/New_York")).date()
    run(day)
