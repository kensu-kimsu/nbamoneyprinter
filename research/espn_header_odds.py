"""Collect explicitly labelled NBA moneylines from ESPN's public scoreboard/header feeds.

No guessed odds, no stale prices, and no betting when the feed omits moneylines.
"""
import datetime as dt
import json
import urllib.parse
from research.espn_odds_probe import get_json, next_prediction_date
from paper_betting.select_bets import ROOT

DEST = ROOT / "research" / "external_odds"

def convert(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value == 0 or abs(value) < 100:
            return None
        return round(1 + value / 100 if value > 0 else 1 + 100 / abs(value), 6)
    if isinstance(value, str):
        try:
            return convert(int(value.strip().replace("+", "")))
        except ValueError:
            return None
    return None

def prices(obj):
    """Require homeTeamOdds and awayTeamOdds; reject spread/total-only entries."""
    if not isinstance(obj, dict):
        return None
    h, a = obj.get("homeTeamOdds"), obj.get("awayTeamOdds")
    if not isinstance(h, dict) or not isinstance(a, dict):
        return None
    hp, ap = convert(h.get("moneyLine")), convert(a.get("moneyLine"))
    if hp is None or ap is None:
        return None
    provider = obj.get("provider") or {}
    name = provider.get("name") if isinstance(provider, dict) else None
    if not name or not isinstance(name, str):
        return None
    return {"bookmaker": name, "home_decimal": hp, "away_decimal": ap}

def collect(event):
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    sides = {c.get("homeAway"): c.get("team", {}).get("displayName")
             for c in comp.get("competitors", [])}
    if not sides.get("home") or not sides.get("away"):
        return None
    tip = event.get("date")
    try:
        kickoff = dt.datetime.fromisoformat(tip.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if kickoff <= dt.datetime.now(dt.timezone.utc):
        return None
    books = []
    for item in (comp.get("odds") or []) + (event.get("odds") or []):
        p = prices(item)
        if p and not any(b["bookmaker"] == p["bookmaker"] for b in books):
            books.append(p)
    # ESPN event summary may include a separate header with labelled moneylines.
    eid = event.get("id")
    if eid and not books:
        try:
            detail = get_json("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=" + urllib.parse.quote(str(eid)))
            for item in (detail.get("header", {}).get("competitions") or []):
                for odds in item.get("odds") or []:
                    p = prices(odds)
                    if p and not any(b["bookmaker"] == p["bookmaker"] for b in books):
                        books.append(p)
        except Exception as exc:
            print("ESPN header unavailable for", eid, type(exc).__name__)
    return {"home_team": sides["home"], "away_team": sides["away"],
            "kickoff_utc": kickoff.isoformat(), "books": books}

def run():
    day = next_prediction_date()
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=" + day.strftime("%Y%m%d")
    data = get_json(url)
    rows = [row for e in data.get("events", []) if (row := collect(e)) is not None]
    result = {"captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "games": [r for r in rows if r["books"]], "scheduled_future_games": len(rows)}
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "espn_header_normalized.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"source": "ESPN scoreboard/header", "scheduled": len(rows),
                      "verified_priced": len(result["games"])}))
    return bool(result["games"])

if __name__ == "__main__":
    run()
