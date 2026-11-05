"""Optional, best-effort OddsHarvester NBA moneyline capture.

This never guesses undocumented scraper fields. Raw output is retained for
schema inspection; only explicit side-labelled odds enter the betting feed.
"""
import datetime as dt
import json
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo
from paper_betting.select_bets import ROOT, timestamp
from research.espn_odds_probe import next_prediction_date

DEST = ROOT / "research" / "external_odds"

def run():
    day = next_prediction_date()
    DEST.mkdir(parents=True, exist_ok=True)
    raw_path = DEST / "oddsharvester_raw.json"
    cmd = ["oddsharvester", "upcoming", "-s", "basketball",
           "-d", day.strftime("%Y%m%d"), "-m", "home_away",
           "--headless", "-f", "json", "-o", str(raw_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("OddsHarvester unavailable: " + str(exc), file=sys.stderr)
        return False
    if result.returncode:
        print("OddsHarvester failed: " + result.stderr[-1200:], file=sys.stderr)
        return False
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("OddsHarvester output unreadable: " + str(exc), file=sys.stderr)
        return False
    # Some versions emit a top-level array, others wrap a matches array.
    matches = raw if isinstance(raw, list) else raw.get("matches", []) if isinstance(raw, dict) else []
    normalized = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        home, away = item.get("home_team"), item.get("away_team")
        tip = item.get("kickoff_utc") or item.get("start_time_utc")
        if not all(isinstance(v, str) and v for v in (home, away, tip)):
            continue
        try:
            timestamp(tip)
        except ValueError:
            continue
        books = []
        for book in item.get("books", []) if isinstance(item.get("books"), list) else []:
            if not isinstance(book, dict):
                continue
            hp, ap = book.get("home_decimal"), book.get("away_decimal")
            name = book.get("bookmaker")
            if (isinstance(name, str) and name
                    and type(hp) in (int, float) and type(ap) in (int, float)
                    and 1 < hp < 1000 and 1 < ap < 1000):
                books.append({"bookmaker": name, "home_decimal": hp, "away_decimal": ap})
        if books:
            normalized.append({"home_team": home, "away_team": away,
                               "kickoff_utc": tip, "books": books})
    output = {"captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "games": normalized, "raw_matches": len(matches)}
    (DEST / "oddsharvester_normalized.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"raw_matches": len(matches), "verified_side_labelled_matches": len(normalized)}))
    return bool(normalized)

if __name__ == "__main__":
    run()
