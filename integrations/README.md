# Odds-API.io integration (first stage)

This is a **read-only** client for the provider at https://odds-api.io (not the-odds-api.com).
It does not place bets or connect to the existing ML model yet.

## Local usage

Set `ODDS_API_KEY` in your PowerShell session (do not commit the key):

```powershell
$env:ODDS_API_KEY = Read-Host "Odds-API.io key"
python -m integrations.odds_api_io sports
python -m integrations.odds_api_io leagues
```

Find the exact NBA league slug in the `leagues` response. Then:

```powershell
python -m integrations.odds_api_io events --league YOUR_NBA_LEAGUE_SLUG
python -m integrations.odds_api_io odds --event-id EVENT_ID --bookmakers Sportsbet,TAB
```

The odds command defaults to Sportsbet, TAB, Ladbrokes, Neds. Access depends on your plan and provider naming. The code deliberately does not assume a league slug or an odds response shape before testing the account.

**Security:** API key is never printed by this client; avoid pasting raw request URLs or secrets into issues/logs. GitHub Actions secret `ODDS_API_KEY` is available only to workflows explicitly passing it as an environment variable. This integration does not yet add an automated workflow, to avoid unintended API charges.

**Next stages:** confirm event/odds response formats, map NBA team names and bookmaker markets, connect predictions, add paper-betting ledger and tests.
