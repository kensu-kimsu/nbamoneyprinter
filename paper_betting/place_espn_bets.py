"""Place virtual-only NBA bets from verified ESPN team-specific moneyline prices."""
import csv
import datetime as dt
import json
import pathlib
from paper_betting.select_bets import ROOT, LEDGER, PRED_DIR, HEADERS, bankroll, timestamp, norm

ODDS_DIR=ROOT/"research/espn_odds_snapshots"
DECISION_DIR=ROOT/"paper_betting/decision_reports"

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
    decisions=[]
    for p in preds:
        decision={"game_id":str(p["game_id"]),"game":str(p.get("away_team",""))+" @ "+str(p.get("home_team","")),
                  "predicted_winner":None,"model_win_probability":None,"best_bookmaker":None,
                  "best_decimal_odds":None,"expected_value_pct":None,"reason":None}
        hp,ap=p.get("home_win_probability"),p.get("away_win_probability")
        if type(hp) in (int,float) and type(ap) in (int,float) and 0<hp<1 and 0<ap<1:
            side="home" if hp>=ap else "away"
            decision["predicted_winner"]=p.get(side+"_team")
            decision["model_win_probability"]=round(p[side+"_win_probability"],6)
        decisions.append(decision)
        gid=str(p["game_id"])
        if gid in already:
            decision["reason"]="duplicate_game_in_ledger"
            continue
        if timestamp(p["game_time_utc"])<=now:
            decision["reason"]="game_already_started"
            continue
        g=by_id.get(gid)
        if not g:
            decision["reason"]="no_odds_game_match"
            continue
        if norm(g["home"])!=norm(p["home_team"]) or norm(g["away"])!=norm(p["away_team"]):
            decision["reason"]="team_name_mismatch"
            continue
        if abs((timestamp(g["tipoff_utc"])-timestamp(p["game_time_utc"])).total_seconds())>60:
            decision["reason"]="tipoff_mismatch"
            continue
        best=None
        for book in g.get("books",[]):
            if not book.get("bookmaker") or book["bookmaker"]=="unknown":
                continue
            for side in ("home","away"):
                price=book.get(side+"_decimal")
                probability=p.get(side+"_win_probability")
                if not isinstance(price,(int,float)) or not isinstance(probability,(int,float)) or price<=1 or not 0<probability<1:
                    continue
                edge=probability*price-1
                if best is None or edge>best[0]:
                    best=(edge,book,side,price,probability)
                if edge>=.05:
                    eligible.append((edge,p,g,book,side,price,probability))
        if best is None:
            decision["reason"]="no_valid_team_side_prices"
        else:
            edge,book,side,price,probability=best
            decision.update({"best_bookmaker":book["bookmaker"],"best_selection":g[side],
                             "best_decimal_odds":price,"best_selection_probability":round(probability,6),
                             "expected_value_pct":round(edge*100,3),
                             "reason":"eligible_positive_ev" if edge>=.05 else "below_5_percent_ev"})
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
        for decision in decisions:
            if decision["game_id"]==gid:
                decision["reason"]="paper_bet_placed"
                decision["placed_selection"]=selection
                decision["placed_bookmaker"]=book["bookmaker"]
                decision["placed_decimal_odds"]=price
                decision["stake_aud"]=stake
                break
        already.add(gid)
        remaining=round(remaining-stake,2)
    for decision in decisions:
        if decision["reason"]=="eligible_positive_ev":
            decision["reason"]="exposure_limit_or_higher_ev_selection"
    DECISION_DIR.mkdir(parents=True,exist_ok=True)
    report_path=DECISION_DIR/("decisions-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
    report_path.write_text(json.dumps({"generated_at_utc":now.isoformat(),
        "odds_captured_at_utc":snapshot["captured_at_utc"],"min_ev_pct":5,
        "bankroll_aud":balance,"available_exposure_aud":max(0,round(balance*.05-open_stakes,2)),
        "decisions":decisions},indent=2)+"\\n",encoding="utf-8")
    if placed:
        with LEDGER.open("a",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=HEADERS)
            writer.writerows(placed)
    report={"source":"Verified ESPN and validated external team-side odds","predictions":len(preds),
            "priced_games":snapshot["games_with_verified_team_side_odds"],
            "eligible_opportunities":len(eligible),"paper_bets_created":len(placed),
            "starting_bankroll_aud":balance,"decision_report":str(report_path.relative_to(ROOT)),
            "decision_reasons":{reason:sum(d["reason"]==reason for d in decisions) for reason in sorted(set(d["reason"] for d in decisions))},
            "bets":[{"game":b["away_team"]+" @ "+b["home_team"],
            "pick":b["selection"],"odds":b["decimal_odds"],"stake_aud":b["stake_aud"]} for b in placed]}
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    run()
