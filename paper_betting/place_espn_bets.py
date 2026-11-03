"""Place virtual-only NBA bets from verified ESPN team-specific moneyline prices."""
import csv
import datetime as dt
import json
import pathlib
from paper_betting.select_bets import ROOT, LEDGER, PRED_DIR, HEADERS, bankroll, timestamp, norm

ODDS_DIR=ROOT/"research/espn_odds_snapshots"

def run(now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    preds=json.loads(max(PRED_DIR.glob("predictions-*.json")).read_text())["predictions"]
    snapshot=json.loads(max(ODDS_DIR.glob("espn-odds-*.json")).read_text())
    captured=timestamp(snapshot["captured_at_utc"])
    if captured>now or (now-captured).total_seconds()>6*3600:
        raise RuntimeError("ESPN odds are older than six hours; no bets recorded")
    with LEDGER.open(newline="") as f:
        existing=list(csv.DictReader(f))
    balance=bankroll(existing)
    open_stakes=sum(float(r["stake_aud"]) for r in existing if r["status"]=="open")
    remaining=max(0,round(balance*.05-open_stakes,2))
    already={r["game_id"] for r in existing}
    by_id={str(g["game_id"]):g for g in snapshot["games"]}
    eligible=[]
    for p in preds:
        gid=str(p["game_id"])
        if gid in already or timestamp(p["game_time_utc"])<=now:
            continue
        g=by_id.get(gid)
        if not g or norm(g["home"])!=norm(p["home_team"]) or norm(g["away"])!=norm(p["away_team"]):
            continue
        if abs((timestamp(g["tipoff_utc"])-timestamp(p["game_time_utc"])).total_seconds())>60:
            continue
        for book in g.get("books",[]):
            if not book.get("bookmaker") or book["bookmaker"]=="unknown":
                continue
            for side in ("home","away"):
                price=book.get(side+"_decimal")
                probability=p.get(side+"_win_probability")
                if not isinstance(price,(int,float)) or not isinstance(probability,(int,float)) or price<=1 or not 0<probability<1:
                    continue
                edge=probability*price-1
                if edge>=.05:
                    eligible.append((edge,p,g,book,side,price,probability))
    eligible.sort(key=lambda x:x[0],reverse=True)
    placed=[]
    for edge,p,g,book,side,price,probability in eligible:
        gid=str(p["game_id"])
        if gid in already:
            continue
        stake=min(round(balance*.01,2),remaining)
        if stake<.01:
            break
        selection=g[side]
        bet={"bet_id":"espn-"+gid+"-"+side,"game_id":gid,"game_time_utc":p["game_time_utc"],
             "home_team":g["home"],"away_team":g["away"],"market":"NBA_H2H",
             "selection":selection,"line":"","bookmaker":book["bookmaker"],
             "decimal_odds":price,"model_probability":probability,"stake_aud":stake,
             "placed_at_utc":now.isoformat(),"status":"open","result":"","profit_aud":"",
             "bankroll_aud":""}
        placed.append(bet)
        already.add(gid)
        remaining=round(remaining-stake,2)
    if placed:
        with LEDGER.open("a",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=HEADERS)
            writer.writerows(placed)
    report={"source":"ESPN explicit home/away DraftKings odds","predictions":len(preds),
            "priced_games":snapshot["games_with_verified_team_side_odds"],
            "eligible_opportunities":len(eligible),"paper_bets_created":len(placed),
            "starting_bankroll_aud":balance,"bets":[{"game":b["away_team"]+" @ "+b["home_team"],
            "pick":b["selection"],"odds":b["decimal_odds"],"stake_aud":b["stake_aud"]} for b in placed]}
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    run()
