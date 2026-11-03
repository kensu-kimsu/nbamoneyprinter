# Seven-day paper-betting experiment

Starting virtual bankroll: **A$100**. No real wagers are placed.

The `ledger.csv` file is the source of truth. One row per paper bet, recorded **before tip-off**. Set `status` to `pending` when recorded; later settle as `won`, `lost`, `push`, or `void`. Use decimal odds, actual simulated stake in AUD, signed `profit_aud`, and running `bankroll_aud`. Do not fabricate bets, predictions, or results.

Run `python -m paper_betting.plot_bankroll` to regenerate `bankroll.svg` from settled entries. A workflow also regenerates the graph whenever `ledger.csv` changes on master.

**Important:** Odds snapshots are being collected separately. The current NBA prediction pipeline is **not yet connected** to HaterPicks or the ledger, and result settlement is **not yet automated**. The chart will remain flat at A$100 until genuine settled paper bets exist. The 7-day test cannot be described as a model-performance test until predictions are timestamped before games and settled afterward.
