"""Merge free public ESPN prices with optional OddsHarvester NBA moneyline output.

Only unambiguously paired home/away bookmaker prices are accepted. The external
scraper runs separately and may return no data because of access restrictions.
"""
import datetime as dt
import json
import pathlib
from paper_betting.select_bets import ROOT, norm, timestamp
from research.espn_odds_probe import run as espn_run

OUT = ROOT / "research" / "espn_odds_snapshots"
EXTERNAL = ROOT / "research" / "external_odds"

def parse_external(row):
    """Require explicit team sides; never infer outcome order from unlabeled arrays."""
    if not isinstance(row, dict):
        return None
    home = row.get("home_team")
    away = row.get("away_team")
    tip = row.get("kickoff_utc") or row.get("start_time_utc")
    if not all(isinstance(x, str) and x for x in (home, away, tip)):
        return None
    try:
        tip = timestamp(tip)
    except (ValueError, TypeError):
        return None
    books = []
    # Only accept explicit side-labelled odds. Unknown OddsHarvester schemas
    # must not be guessed, as that can reverse a bet's selection.
    entries = row.get("books")
    if not isinstance(entries, list):
        return None
    for b in entries:
        if not isinstance(b, dict):
            continue
        name = b.get("bookmaker")
        hp, ap = b.get("home_decimal"), b.get("away_decimal")
        if (isinstance(name, str) and name and name != "unknown"
                and type(hp) in (float, int) and type(ap) in (float, int)
                and 1 < hp < 1000 and 1 < ap < 1000):
            books.append({"bookmaker": name, "home_decimal": hp,
                          "away_decimal": ap, "source": "external_verified"})
    return {"home": home, "away": away, "tipoff_utc": tip, "books": books}

def run():
    # ESPN can return a partial slate; a failed ESPN price request must not
    # stop other sources from being considered.
    try:
        espn_run()
    except RuntimeError as exc:
        print("ESPN partial/empty: " + str(exc))
    files = sorted(OUT.glob("espn-odds-*.json"))
    if not files:
        raise RuntimeError("No ESPN slate available to anchor verified game IDs")
    base = json.loads(files[-1].read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    if abs((now - timestamp(base["captured_at_utc"])).total_seconds()) > 3600:
        raise RuntimeError("ESPN schedule snapshot is stale")
    added = 0
    errors = []
    for file in sorted(EXTERNAL.glob("*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
                continue
            captured = timestamp(payload["captured_at_utc"])
            if captured > now or (now - captured).total_seconds() > 3600:
                continue
            for raw in payload["games"]:
                parsed = parse_external(raw)
                if not parsed or parsed["tipoff_utc"] <= captured:
                    continue
                matches = [g for g in base["games"]
                           if norm(g["home"]) == norm(parsed["home"])
                           and norm(g["away"]) == norm(parsed["away"])
                           and abs((timestamp(g["tipoff_utc"]) - parsed["tipoff_utc"]).total_seconds()) <= 60]
                if len(matches) != 1:
                    continue
                for book in parsed["books"]:
                    if not any(b["bookmaker"] == book["bookmaker"] for b in matches[0]["books"]):
                        matches[0]["books"].append(book)
                        added += 1
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({"file": file.name, "error": str(exc)[:100]})
    base["captured_at_utc"] = now.isoformat()
    base["games_with_verified_team_side_odds"] = sum(bool(g["books"]) for g in base["games"])
    base["source"] = "ESPN + validated external snapshots"
    base["external_prices_added"] = added
    base["external_errors"] = errors
    base["missing_games"] = [{"game_id": g["game_id"], "match": g["away"] + " @ " + g["home"]}
                             for g in base["games"] if not g["books"]]
    base["coverage_pct"] = round(100 * base["games_with_verified_team_side_odds"] /
                                  len(base["games"]), 2) if base["games"] else 0
    path = OUT / ("espn-odds-" + now.strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"priced": base["games_with_verified_team_side_odds"],
                      "scheduled": len(base["games"]), "coverage_pct": base["coverage_pct"],
                      "external_prices_added": added, "missing_games": base["missing_games"]}, indent=2))
    if not base["games_with_verified_team_side_odds"]:
        raise RuntimeError("No verified prices from any source")
    return base

if __name__ == "__main__":
    run()
