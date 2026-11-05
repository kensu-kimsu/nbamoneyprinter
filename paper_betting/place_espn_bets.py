"""Auditable, virtual-only NBA bets and slate-scoped decision reports."""
import csv
import datetime as dt
import json
from paper_betting.select_bets import ROOT, LEDGER, PRED_DIR, HEADERS, bankroll, timestamp, norm

ODDS_DIR = ROOT / "research/espn_odds_snapshots"
DECISION_DIR = ROOT / "paper_betting/decision_reports"
MIN_EV = .05

def valid_number(value):
    return type(value) in (float, int)

def best_prices(pred, game):
    """Evaluate both sides independently, retaining the highest-EV valid quote."""
    candidates = []
    for book in game.get("books", []):
        name = book.get("bookmaker")
        if not isinstance(name, str) or not name or name == "unknown":
            continue
        for side in ("home", "away"):
            price, probability = book.get(side + "_decimal"), pred.get(side + "_win_probability")
            if not (valid_number(price) and 1 < price < 1000 and valid_number(probability) and 0 < probability < 1):
                continue
            candidates.append({"side":side,"selection":game[side],"bookmaker":name,
                "decimal_odds":price,"probability":probability,"ev":probability*price-1})
    candidates.sort(key=lambda x:x["ev"], reverse=True)
    return candidates

def run(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    preds = json.loads(max(PRED_DIR.glob("predictions-*.json")).read_text())["predictions"]
    snapshot = json.loads(max(ODDS_DIR.glob("espn-odds-*.json")).read_text())
    captured = timestamp(snapshot["captured_at_utc"])
    if captured > now or (now-captured).total_seconds() > 6*3600:
        raise RuntimeError("Odds snapshot is stale; no virtual bets recorded")
    with LEDGER.open(newline="") as f:
        existing = list(csv.DictReader(f))
    balance = bankroll(existing)
    open_stakes = sum(float(r["stake_aud"]) for r in existing if r["status"] == "open")
    initial_exposure = max(0, round(balance*.05-open_stakes,2))
    remaining = initial_exposure
    already = {str(r["game_id"]) for r in existing}
    by_id = {str(g["game_id"]):g for g in snapshot["games"]}
    decisions, eligible = [], []
    for pred in preds:
        gid = str(pred["game_id"])
        tip = timestamp(pred["game_time_utc"])
        hp, ap = pred.get("home_win_probability"), pred.get("away_win_probability")
        winner_side = ("home" if hp >= ap else "away") if (valid_number(hp) and valid_number(ap)) else None
        d = {"game_id":gid,"game":pred["away_team"]+" @ "+pred["home_team"],
             "game_time_utc":pred["game_time_utc"],
             "predicted_winner":pred.get(winner_side+"_team") if winner_side else None,
             "model_win_probability":pred.get(winner_side+"_win_probability") if winner_side else None,
             "predicted_winner_quote":None,"best_ev_quote":None,"reason":None}
        decisions.append(d)
        if tip <= now:
            d["category"]="historical_or_started"
            d["reason"]="game_already_started"
            continue
        d["category"]="upcoming"
        game = by_id.get(gid)
        if not game:
            d["reason"]="not_in_current_odds_slate"
            continue
        if norm(game["home"]) != norm(pred["home_team"]) or norm(game["away"]) != norm(pred["away_team"]):
            d["reason"]="team_name_mismatch"
            continue
        if abs((timestamp(game["tipoff_utc"])-tip).total_seconds()) > 60:
            d["reason"]="tipoff_mismatch"
            continue
        d["category"]="current_priced_slate" if game.get("books") else "current_unpriced_slate"
        quotes = best_prices(pred,game)
        if winner_side:
            winner_quotes = [q for q in quotes if q["side"]==winner_side]
            if winner_quotes:
                q = max(winner_quotes,key=lambda q:q["decimal_odds"])
                d["predicted_winner_quote"] = {"bookmaker":q["bookmaker"],"decimal_odds":q["decimal_odds"],
                                               "expected_value_pct":round(q["ev"]*100,3)}
        if quotes:
            q = quotes[0]
            d["best_ev_quote"] = {"selection":q["selection"],"bookmaker":q["bookmaker"],
                 "decimal_odds":q["decimal_odds"],"model_probability":round(q["probability"],6),
                 "expected_value_pct":round(q["ev"]*100,3)}
        if gid in already:
            d["reason"]="duplicate_game_in_ledger"
        elif not quotes:
            d["reason"]="no_valid_team_side_prices"
        elif quotes[0]["ev"] < MIN_EV:
            d["reason"]="below_5_percent_ev"
        else:
            d["reason"]="eligible_positive_ev"
            eligible.append((quotes[0]["ev"],pred,game,quotes[0],d))
    eligible.sort(key=lambda item:item[0],reverse=True)
    placed = []
    for edge,pred,game,q,d in eligible:
        gid = str(pred["game_id"])
        if gid in already:
            d["reason"]="duplicate_game_in_ledger"
            continue
        stake = min(round(balance*.01,2),remaining)
        if stake < .01:
            d["reason"]="exposure_limit_reached"
            continue
        bet = {"bet_id":"espn-"+gid+"-"+q["side"],"game_id":gid,"game_time_utc":pred["game_time_utc"],
            "home_team":game["home"],"away_team":game["away"],"market":"NBA_H2H",
            "selection":q["selection"],"line":"","bookmaker":q["bookmaker"],
            "decimal_odds":q["decimal_odds"],"model_probability":q["probability"],
            "stake_aud":stake,"placed_at_utc":now.isoformat(),"status":"open",
            "result":"","profit_aud":"","bankroll_aud":""}
        placed.append(bet)
        d["reason"]="paper_bet_placed"
        d["placed_selection"]=q["selection"]
        d["stake_aud"]=stake
        already.add(gid)
        remaining=round(remaining-stake,2)
    if placed:
        with LEDGER.open("a",newline="") as f:
            csv.DictWriter(f,fieldnames=HEADERS).writerows(placed)
    counts = {}
    reasons = {}
    for d in decisions:
        counts[d["category"]] = counts.get(d["category"],0)+1
        reasons[d["reason"]] = reasons.get(d["reason"],0)+1
    DECISION_DIR.mkdir(parents=True,exist_ok=True)
    report_path=DECISION_DIR/("decisions-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
    report={"generated_at_utc":now.isoformat(),"odds_captured_at_utc":snapshot["captured_at_utc"],
        "min_ev_pct":5,"bankroll_aud":balance,"available_exposure_aud":initial_exposure,
        "category_counts":counts,"decision_reasons":reasons,"decisions":decisions}
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    summary={"source":"Verified ESPN and validated external team-side odds","predictions":len(preds),
        "priced_games":snapshot["games_with_verified_team_side_odds"],"eligible_opportunities":len(eligible),
        "paper_bets_created":len(placed),"starting_bankroll_aud":balance,
        "decision_report":str(report_path.relative_to(ROOT)),"category_counts":counts,
        "decision_reasons":reasons,"bets":[{"game":b["away_team"]+" @ "+b["home_team"],
            "pick":b["selection"],"odds":b["decimal_odds"],"stake_aud":b["stake_aud"]} for b in placed]}
    print(json.dumps(summary,indent=2))
    return summary

if __name__=="__main__":
    run()
