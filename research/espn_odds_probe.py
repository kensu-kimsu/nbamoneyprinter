"""Probe ESPN's public NBA odds for the same games used by our predictor.

Only accept explicit homeTeamOdds/awayTeamOdds moneyLine fields. No wagers.
"""
import datetime as dt
import json
import pathlib
import urllib.request
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"research/espn_odds_snapshots"

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Paper-Research/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as response:
        return json.load(response)

def american_to_decimal(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or value==0 or abs(value)<100:
        return None
    return round(1+value/100 if value>0 else 1+100/abs(value),6)

def run(day=None):
    day=day or dt.datetime.now(ZoneInfo("America/New_York")).date()
    payload=get_json("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates="+day.strftime("%Y%m%d"))
    events=payload.get("events",[])
    now=dt.datetime.now(dt.timezone.utc)
    rows=[]
    for event in events:
        competitions=event.get("competitions") or []
        if not competitions:
            continue
        competition=competitions[0]
        teams={item.get("homeAway"):item.get("team",{}).get("displayName") for item in competition.get("competitors",[])}
        game_id=str(event.get("id",""))
        if not game_id or not teams.get("home") or not teams.get("away"):
            continue
        try:
            tipoff=dt.datetime.fromisoformat(event["date"].replace("Z","+00:00"))
        except (KeyError,ValueError):
            continue
        if tipoff<=now:
            continue
        url=f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{game_id}/competitions/{competition.get('id',game_id)}/odds"
        record={"game_id":game_id,"home":teams["home"],"away":teams["away"],"tipoff_utc":tipoff.isoformat(),"books":[]}
        try:
            data=get_json(url)
            for item in data.get("items",[]):
                h=item.get("homeTeamOdds") or {}
                a=item.get("awayTeamOdds") or {}
                hp=american_to_decimal(h.get("moneyLine"))
                ap=american_to_decimal(a.get("moneyLine"))
                if hp is None or ap is None:
                    continue
                record["books"].append({"bookmaker":(item.get("provider") or {}).get("name","unknown"),
                    "home_decimal":hp,"away_decimal":ap,
                    "home_american":h["moneyLine"],"away_american":a["moneyLine"]})
        except Exception as exc:
            record["error"]=type(exc).__name__+": "+str(exc)[:150]
        rows.append(record)
    result={"captured_at_utc":now.isoformat(),"date_us_eastern":str(day),"scheduled_future_games":len(rows),
        "games_with_verified_team_side_odds":sum(bool(x["books"]) for x in rows),
        "games":rows,"paper_bets_enabled":False}
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/("espn-odds-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
    path.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"report":str(path),"scheduled_future_games":result["scheduled_future_games"],
        "games_with_verified_team_side_odds":result["games_with_verified_team_side_odds"]},indent=2))
    return result

if __name__=="__main__":
    run()
