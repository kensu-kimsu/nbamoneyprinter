"""Compare actual filtered paper bets with hypothetical bets on every AI winner.

No fabricated prices: hypothetical bets require a verified pre-tipoff bookmaker
moneyline for the model's chosen team. Missing prices are reported as unpriced.
"""
import csv
import json
from collections import defaultdict
from paper_betting.select_bets import ROOT, norm, timestamp

OUT = ROOT / "research" / "prediction_results"
ODDS = ROOT / "research" / "espn_odds_snapshots"
LEDGER = ROOT / "paper_betting" / "ledger.csv"

def run():
    with (OUT / "all_predictions.csv").open(newline="", encoding="utf-8") as f:
        predictions = list(csv.DictReader(f))
    with LEDGER.open(newline="", encoding="utf-8") as f:
        bets = list(csv.DictReader(f))
    prices = defaultdict(list)
    for file in sorted(ODDS.glob("espn-odds-*.json")):
        try:
            snap = json.loads(file.read_text(encoding="utf-8"))
            captured = timestamp(snap["captured_at_utc"])
            for game in snap.get("games", []):
                tip = timestamp(game["tipoff_utc"])
                if captured >= tip:
                    continue
                for book in game.get("books", []):
                    for side in ("home", "away"):
                        price = book.get(side + "_decimal")
                        if (isinstance(price, (int, float)) and not isinstance(price, bool)
                                and price > 1 and book.get("bookmaker") not in (None, "", "unknown")):
                            prices[str(game["game_id"])].append({
                                "captured": captured, "tip": tip, "side": side,
                                "price": float(price), "bookmaker": book["bookmaker"],
                                "home": game["home"], "away": game["away"]
                            })
        except (ValueError, OSError, KeyError, TypeError):
            continue

    # Use earliest recorded valid pre-tipoff price for a deterministic, no-lookahead
    # comparison. Later snapshots cannot retroactively improve a historical result.
    hypothetical = []
    balance = 100.0
    for pred in sorted(predictions, key=lambda r: (r["game_time_utc"], r["game_id"])):
        gid = str(pred["game_id"])
        side = ("home" if norm(pred["predicted_winner"]) == norm(pred["home_team"]) else "away")
        options = [o for o in prices[gid] if o["side"] == side
                   and norm(o["home"]) == norm(pred["home_team"])
                   and norm(o["away"]) == norm(pred["away_team"])
                   and abs((o["tip"] - timestamp(pred["game_time_utc"])).total_seconds()) <= 60]
        options.sort(key=lambda o: (o["captured"], o["bookmaker"]))
        selected = options[0] if options else None
        status = pred["status"]
        row = {"game_id": gid, "game_time_utc": pred["game_time_utc"],
               "predicted_winner": pred["predicted_winner"], "actual_winner": pred["actual_winner"],
               "result_status": status, "bookmaker": selected["bookmaker"] if selected else "",
               "odds_captured_at_utc": selected["captured"].isoformat() if selected else "",
               "decimal_odds": selected["price"] if selected else "",
               "stake_aud": "", "profit_aud": "", "bankroll_aud": "",
               "simulation_status": "unpriced" if not selected else "awaiting_final"}
        if selected and status == "final":
            stake = round(balance * .01, 2)
            won = norm(pred["predicted_winner"]) == norm(pred["actual_winner"])
            profit = round(stake * (selected["price"] - 1), 2) if won else -stake
            balance = round(balance + profit, 2)
            row.update(stake_aud=f"{stake:.2f}", profit_aud=f"{profit:.2f}",
                       bankroll_aud=f"{balance:.2f}", simulation_status="won" if won else "lost")
        hypothetical.append(row)

    settled = [b for b in bets if b["status"] == "settled" and b.get("profit_aud")]
    actual_profit = round(sum(float(b["profit_aud"]) for b in settled), 2)
    simulated = [r for r in hypothetical if r["simulation_status"] in ("won", "lost")]
    summary = {
        "starting_bankroll_aud": 100.0,
        "filtered_actual": {
            "settled_bets": len(settled),
            "wins": sum(b["result"] == "won" for b in settled),
            "losses": sum(b["result"] == "lost" for b in settled),
            "profit_aud": actual_profit,
            "bankroll_aud": round(100 + actual_profit, 2),
            "open_bets": sum(b["status"] == "open" for b in bets)
        },
        "all_ai_winners_hypothetical": {
            "total_predictions": len(predictions),
            "completed_games": sum(r["status"] == "final" for r in predictions),
            "priced_completed_games": len(simulated),
            "completed_games_without_verified_odds": sum(
                r["result_status"] == "final" and r["simulation_status"] == "unpriced"
                for r in hypothetical),
            "wins": sum(r["simulation_status"] == "won" for r in simulated),
            "losses": sum(r["simulation_status"] == "lost" for r in simulated),
            "profit_aud": round(balance - 100, 2),
            "bankroll_aud": round(balance, 2)
        },
        "comparison_caveat": "The all-picks hypothetical is restricted to games with saved, "
            "verified pre-tipoff prices. Unpriced games are excluded, not assigned invented "
            "odds or zero-profit bets. Each settled hypothetical bet risks 1% of its "
            "simulated bankroll, compounded in scheduled tipoff order. It does not model "
            "the actual strategy's 5% concurrent exposure limit or real-time bet "
            "availability. This is an illustrative counterfactual, not a directly "
            "equivalent execution backtest."
    }
    fields = ["game_id", "game_time_utc", "predicted_winner", "actual_winner",
              "result_status", "bookmaker", "odds_captured_at_utc", "decimal_odds",
              "stake_aud", "profit_aud", "bankroll_aud", "simulation_status"]
    with (OUT / "all_picks_hypothetical.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(hypothetical)
    (OUT / "bankroll_comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary

if __name__ == "__main__":
    run()
