"""Audit every saved pregame NBA prediction against ESPN final scores.

Keeps the earliest valid pre-tipoff prediction for each game to avoid hindsight.
This is independent of whether the game qualified for a paper bet.
"""
import csv
import datetime as dt
import json
import pathlib
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

from paper_betting.select_bets import ROOT, LEDGER, norm, timestamp

PRED_DIR = ROOT / "research" / "live_predictions"
OUT_DIR = ROOT / "research" / "prediction_results"
COLUMNS = ["game_id", "game_time_utc", "home_team", "away_team",
           "predicted_at_utc", "predicted_winner", "confidence",
           "home_win_probability", "away_win_probability", "actual_winner",
           "home_score", "away_score", "status", "correct",
           "paper_bet_selection", "paper_bet_status", "paper_bet_profit_aud"]


def fetch_scoreboard(day):
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
           "scoreboard?dates=" + day.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response).get("events", [])


def verified_result(event, prediction):
    if str(event.get("id")) != str(prediction["game_id"]):
        return None
    state = event.get("status", {}).get("type", {})
    if state.get("completed") is not True or state.get("state") != "post":
        return None
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    sides = {x.get("homeAway"): x for x in competitions[0].get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None
    home, away = sides["home"], sides["away"]
    if norm(home.get("team", {}).get("displayName")) != norm(prediction["home_team"]):
        return None
    if norm(away.get("team", {}).get("displayName")) != norm(prediction["away_team"]):
        return None
    try:
        hs, aws = int(home["score"]), int(away["score"])
    except (KeyError, ValueError, TypeError):
        return None
    if hs == aws:
        return None
    return (prediction["home_team"] if hs > aws else prediction["away_team"], hs, aws)


def run(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    earliest = {}
    skipped = 0
    for path in sorted(PRED_DIR.glob("predictions-*.json")):
        try:
            predictions = json.loads(path.read_text(encoding="utf-8"))["predictions"]
        except (ValueError, KeyError, OSError):
            skipped += 1
            continue
        for pred in predictions:
            try:
                gid = str(pred["game_id"])
                tip = timestamp(pred["game_time_utc"])
                created = timestamp(pred["predicted_at_utc"])
                home_p = float(pred["home_win_probability"])
                away_p = float(pred["away_win_probability"])
                if created >= tip or not 0 <= home_p <= 1 or not 0 <= away_p <= 1:
                    skipped += 1
                    continue
                if abs(home_p + away_p - 1) > .01:
                    skipped += 1
                    continue
                if gid not in earliest or created < timestamp(earliest[gid]["predicted_at_utc"]):
                    earliest[gid] = pred
            except (KeyError, ValueError, TypeError):
                skipped += 1

    with LEDGER.open(newline="", encoding="utf-8") as f:
        bets = list(csv.DictReader(f))
    bet_by_game = {str(b["game_id"]): b for b in bets}
    dates = {timestamp(p["game_time_utc"]).astimezone(
        ZoneInfo("America/New_York")).date()
        for p in earliest.values() if timestamp(p["game_time_utc"]) <= now}
    events = {}
    fetch_errors = []
    for day in sorted(dates):
        try:
            for event in fetch_scoreboard(day):
                events[str(event.get("id"))] = event
        except (OSError, ValueError, KeyError) as exc:
            fetch_errors.append({"date": str(day), "error": str(exc)[:160]})

    rows = []
    for gid, p in sorted(earliest.items(), key=lambda kv: (kv[1]["game_time_utc"], kv[0])):
        home_p, away_p = float(p["home_win_probability"]), float(p["away_win_probability"])
        pick = p["home_team"] if home_p >= away_p else p["away_team"]
        result = verified_result(events[gid], p) if gid in events else None
        tip = timestamp(p["game_time_utc"])
        status = "final" if result else ("scheduled" if tip > now else "awaiting_final")
        bet = bet_by_game.get(gid, {})
        rows.append({
            "game_id": gid, "game_time_utc": p["game_time_utc"],
            "home_team": p["home_team"], "away_team": p["away_team"],
            "predicted_at_utc": p["predicted_at_utc"], "predicted_winner": pick,
            "confidence": round(max(home_p, away_p), 6),
            "home_win_probability": home_p, "away_win_probability": away_p,
            "actual_winner": result[0] if result else "",
            "home_score": result[1] if result else "",
            "away_score": result[2] if result else "",
            "status": status,
            "correct": int(norm(pick) == norm(result[0])) if result else "",
            "paper_bet_selection": bet.get("selection", ""),
            "paper_bet_status": bet.get("status", ""),
            "paper_bet_profit_aud": bet.get("profit_aud", ""),
        })
    finished = [r for r in rows if r["status"] == "final"]
    correct = sum(r["correct"] for r in finished)
    settled = [b for b in bets if b["status"] == "settled" and b.get("profit_aud")]
    profit = round(sum(float(b["profit_aud"]) for b in settled), 2)
    summary = {
        "generated_at_utc": now.isoformat(),
        "unique_pregame_predictions": len(rows),
        "final_games": len(finished),
        "correct_predictions": correct,
        "incorrect_predictions": len(finished) - correct,
        "accuracy_pct": round(100 * correct / len(finished), 2) if finished else None,
        "awaiting_final": sum(r["status"] == "awaiting_final" for r in rows),
        "upcoming": sum(r["status"] == "scheduled" for r in rows),
        "settled_paper_bets": len(settled),
        "paper_bet_wins": sum(b.get("result") == "won" for b in settled),
        "paper_bet_losses": sum(b.get("result") == "lost" for b in settled),
        "paper_bet_profit_aud": profit,
        "paper_bankroll_aud": round(100 + profit, 2),
        "open_paper_bets": sum(b["status"] == "open" for b in bets),
        "scoreboard_fetch_errors": fetch_errors,
        "invalid_or_unreadable_predictions_skipped": skipped,
        "methodology": "Earliest saved prediction before tipoff per ESPN game ID; "
                       "accuracy uses the model's highest-probability winner, "
                       "not necessarily its value-bet selection. Final scores "
                       "require ESPN completed status and matching teams."
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "all_predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
