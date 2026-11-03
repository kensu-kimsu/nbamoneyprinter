"""Read-only diagnostic for the 2026-27 pregame prediction integration.

Does not invent model features, probabilities, odds, or simulated bets.
Prints schema metadata only; no API secrets or raw odds payload.
"""
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def nba_stats():
    params = {
        "Conference": "", "DateFrom": "", "DateTo": "", "Division": "",
        "GameScope": "", "GameSegment": "", "LastNGames": "0",
        "LeagueID": "00", "Location": "", "MeasureType": "Base",
        "Month": "0", "OpponentTeamID": "0", "Outcome": "",
        "PORound": "0", "PaceAdjust": "N", "PerMode": "PerGame",
        "Period": "0", "PlayerExperience": "", "PlayerPosition": "",
        "PlusMinus": "N", "Rank": "N", "Season": "2026-27",
        "SeasonSegment": "", "SeasonType": "Regular Season",
        "ShotClockRange": "", "StarterBench": "", "TeamID": "0",
        "TwoWay": "", "VsConference": "", "VsDivision": "",
    }
    url = "https://stats.nba.com/stats/leaguedashteamstats?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.load(response)
    sets = payload.get("resultSets") or payload.get("resultSet")
    if isinstance(sets, dict):
        sets = [sets]
    if not isinstance(sets, list) or not sets:
        raise RuntimeError("Unexpected NBA stats response")
    first = sets[0]
    return first.get("headers", []), first.get("rowSet", [])


def main():
    from research.predict import find_model
    import xgboost as xgb
    path = find_model()
    booster = xgb.Booster()
    booster.load_model(str(path))
    print("MODEL", json.dumps({
        "file": str(path.relative_to(ROOT)),
        "num_features": booster.num_features(),
        "feature_names": booster.feature_names,
        "objective": booster.attr("objective"),
    }))
    snapshots = sorted((ROOT / "research/odds_snapshots").glob("nba-odds-*.json"))
    if not snapshots:
        raise RuntimeError("No committed HaterPicks snapshots; cannot integrate odds")
    snapshot = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    rows = snapshot["payload"]["data"]
    if not rows:
        raise RuntimeError("HaterPicks snapshot has no odds rows")
    sample = rows[0]
    print("ODDS", json.dumps({
        "snapshot": snapshots[-1].name,
        "captured_at_utc": snapshot.get("captured_at_utc"),
        "rows": len(rows),
        "first_row_keys": sorted(sample),
        "field_types": {k: type(v).__name__ for k, v in sample.items()},
        "prices_bookmaker_keys": sorted(sample.get("prices", {})) if isinstance(sample.get("prices"), dict) else [],
    }))
    headers, stats = nba_stats()
    if len(stats) < 25:
        raise RuntimeError(f"Insufficient current-season NBA team stats: {len(stats)}")
    print("STATS", json.dumps({
        "season": "2026-27", "teams": len(stats),
        "columns": headers, "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }))
    print("DIAGNOSTIC COMPLETE. No live model prediction generated or recorded.")


if __name__ == "__main__":
    main()
