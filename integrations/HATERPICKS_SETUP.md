# Free Australian NBA odds provider

Provider: https://www.haterpicks.app/haterpicks-api/nba

HaterPicks advertises a free plan with 1,000 API calls/month and NBA game lines.
Bookmaker coverage and available markets depend on the live feed. This integration
does not place bets or connect to the prediction model yet.

## Setup (browser only)

1. Register for a free API key using the provider's website.
2. Open GitHub repository Settings > Secrets and variables > Actions.
3. Create a repository secret named `HATERPICKS_API_KEY` with the key.
4. Open Actions > Test HaterPicks NBA odds > Run workflow.

The test prints a summary of returned markets, bookmakers, and row count.
It does not print your key or raw response. Empty rows may mean there are no
currently available games or the provider does not supply a particular market.

Local test: set the `HATERPICKS_API_KEY` environment variable and run
`python -m integrations.haterpicks`.

The API returns raw market rows, not model predictions. Do not infer a
profitable betting edge from feed availability alone.
