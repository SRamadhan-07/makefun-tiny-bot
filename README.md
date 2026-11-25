# Tiny Bot — Beat Buy-and-Hold on Solana

[![make.fun bounty](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/SRamadhan-07/makefun-tiny-bot/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/SRamadhan-07/makefun-tiny-bot/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

A Python paper-trading bot for the `agent-fun/bars-replay/v1` protocol. It reads hourly bars for FARTCOIN, JITOSOL, POPCAT, RAY, SOL, WETH and WIF, and tries to beat buy-and-hold by following confirmed uptrends while sitting in USDC the rest of the time.

## Strategy

- **Entry:** fast average (6 bars) above slow average (20 bars) by at least 0.15%, 12-bar momentum at least +0.7%, and a short oscillator below 72 so entries are not chasing a stretched move.
- **Sizing:** about 18% of equity per position (halved for the volatile meme names or after a wild recent swing), at most 4 holdings, always inside the 25% per-symbol weight cap, and shrunk further when pool impact is high.
- **Exits:** trend break (fast below slow), a −4.5% hard stop, or a trailing stop that arms at +5% and gives back 3% from the peak.
- **Drawdown brake:** if equity falls 11% from its peak, everything is sold and new entries pause until the drawdown recovers to 5%.
- **Discipline:** deterministic, no lookahead (signals use only closes already seen; orders fill at the next bar open), a 5-bar cooldown after each exit to avoid fee churn.

## Layout

- `main.py` — the bot (speaks the hello / batch / orders wire protocol via the vendored shim).
- `vendor/makefun_bars.py` — the kit's Python protocol shim, vendored as the SDK instructs.

## Run locally

The grader runs it as `python3 main.py`, feeding protocol lines on stdin and reading one reply per batch on stdout.
