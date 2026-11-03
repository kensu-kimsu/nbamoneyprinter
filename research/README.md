# Permanent prediction history

The file `events.jsonl` is an **append-only event log**. Each line is a JSON event containing a SHA-256 content digest. Commit each update to GitHub to preserve version history; also keep independent backups. GitHub is not an immutable or guaranteed permanent archive: administrators can rewrite history or delete the repository.

**Prediction event**: prediction_id, game_id, game_time_utc, predicted_at_utc, model_version, market, selection, model_probability (0–1), odds_source, decimal_odds, home_team, away_team. Add optional source snapshot ID, model feature version, bookmaker, threshold, expected value, and no-bet decision. Timestamp predictions before tipoff.

**Settlement event**: prediction_id, settled_at_utc, result (won/lost/push/void), final_home_score, final_away_score. Settle only after games start and verify against official results.

`python -m research.history summary` counts events. `python -m research.history predict --file prediction.json` and `python -m research.history settle --file settlement.json` append validated events. The command does **not** generate predictions, fetch results, or place bets.

## Training integrity

- Keep every pregame prediction, including **no-bet** decisions, not only winning or qualifying bets.
- Never edit old predictions to reflect the outcome; add separately timestamped settlement records.
- Preserve model versions and input snapshots for reproducibility.
- Train with historical game features available **before** tipoff, not settlement results or postgame statistics.
- Use walk-forward validation and a held-out recent period. Track calibration, log loss, ROI, closing-line value, drawdown and transaction assumptions.
- The one-week trial is too short to establish profitability. Do not auto-retrain or promote models based on seven days of results.
- The betting ledger and this event log are currently separate; **automatic predictions, settlement, syncing and retraining are not yet implemented**.
