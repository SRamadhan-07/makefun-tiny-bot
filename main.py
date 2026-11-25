"""Tiny guarded momentum bot for the bars-replay hello protocol.

The harness speaks agent-fun/bars-replay/v1: a hello line first, then one
batch of hourly bar data per step, and the bot answers each batch with a
reply holding its orders. Orders decided on one bar fill at the next bar
open, so every signal below uses only closes from bars already seen.

Strategy in one paragraph: follow confirmed uptrends, sit in cash the rest
of the time. A symbol becomes a buy candidate when its fast average sits
above its slow average, its twelve bar momentum is clearly positive, and
its short oscillator is not stretched. Open positions leave on a trend
break, a hard stop, or a trailing stop that locks in a run. A portfolio
drawdown brake parks everything in cash when equity slips too far from
its peak, because beating buy-and-hold on a choppy tape is mostly about
not giving back gains to fees and whipsaws.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

FAST_LEN = 6
SLOW_LEN = 20
MOM_LEN = 12
MOM_MIN = 0.007
SPREAD_MIN = 0.0015
TARGET_WEIGHT = 0.18
MAX_HOLDINGS = 4
STOP_LOSS = -0.045
TRAIL_ARM = 0.05
TRAIL_GIVEBACK = 0.03
DD_BRAKE = 0.11
DD_RESUME = 0.05
COOLDOWN_BARS = 5
SLIPPAGE_BPS = 250

history = {}
entry_close = {}
peak_close = {}
last_exit_seq = {}
peak_equity = [0]
brake_on = [False]

# The meme names swing far harder than the majors on the same tape, so a
# position in one of them starts at half size until it proves itself.
WILD_NAMES = {"FARTCOIN", "POPCAT", "WIF"}


def _recent_swing(symbol, span=12):
    closes = history.get(symbol, [])
    if len(closes) < span:
        return 0.0
    window = closes[-span:]
    return max(window) / min(window) - 1.0


def _push(symbol, close_price):
    closes = history.setdefault(symbol, [])
    closes.append(close_price)
    if len(closes) > 80:
        del closes[:-80]


def _mean(values):
    return sum(values) / len(values)


def _oscillator(closes, span=10):
    window = closes[-span:]
    if len(window) < 3:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(1, len(window)):
        step = window[i] - window[i - 1]
        if step > 0:
            gains += step
        else:
            losses -= step
    if gains + losses == 0:
        return 50.0
    return 100.0 * gains / (gains + losses)


def _signal(symbol):
    closes = history.get(symbol, [])
    if len(closes) < SLOW_LEN + 2:
        return None
    fast = _mean(closes[-FAST_LEN:])
    slow = _mean(closes[-SLOW_LEN:])
    if len(closes) <= MOM_LEN:
        return None
    momentum = closes[-1] / closes[-1 - MOM_LEN] - 1.0
    osc = _oscillator(closes)
    return fast, slow, momentum, osc


def _update_brake(state):
    if state.equity > peak_equity[0]:
        peak_equity[0] = state.equity
    if peak_equity[0] <= 0:
        return
    drawdown = 1.0 - state.equity / peak_equity[0]
    if drawdown >= DD_BRAKE:
        brake_on[0] = True
    elif drawdown <= DD_RESUME:
        brake_on[0] = False


def on_batch(state, batch):
    if state.warming_up:
        for bar in batch["bars"]:
            _push(bar["symbol"], int(bar["c"]))
        return []

    for bar in batch["bars"]:
        _push(bar["symbol"], int(bar["c"]))

    _update_brake(state)
    orders = []

    held = set(state.positions)
    for symbol in list(held):
        close_now = state.close(symbol)
        if close_now is None:
            continue
        if symbol not in peak_close or close_now > peak_close[symbol]:
            peak_close[symbol] = close_now
        sig = _signal(symbol)
        trend_down = sig is not None and sig[0] < sig[1]
        start = entry_close.get(symbol)
        stop_hit = start is not None and close_now / start - 1.0 <= STOP_LOSS
        peak = peak_close.get(symbol, close_now)
        trail_hit = (
            start is not None
            and peak / start - 1.0 >= TRAIL_ARM
            and close_now / peak - 1.0 <= -TRAIL_GIVEBACK
        )
        if brake_on[0] or trend_down or stop_hit or trail_hit:
            qty = state.positions[symbol].qty
            if qty > 0:
                orders.append({
                    "side": "sell",
                    "symbol": symbol,
                    "qty": qty,
                    "max_slippage_bps": SLIPPAGE_BPS,
                })
                last_exit_seq[symbol] = state.seq
                entry_close.pop(symbol, None)
                peak_close.pop(symbol, None)

    if brake_on[0]:
        return orders

    open_slots = MAX_HOLDINGS - (len(held) - sum(1 for o in orders if o["side"] == "sell"))
    if open_slots <= 0:
        return orders

    candidates = []
    for symbol in state.symbols:
        if symbol in state.positions:
            continue
        if state.seq - last_exit_seq.get(symbol, -10 ** 9) < COOLDOWN_BARS:
            continue
        sig = _signal(symbol)
        if sig is None:
            continue
        fast, slow, momentum, osc = sig
        if fast > slow and fast / slow - 1.0 >= SPREAD_MIN and momentum >= MOM_MIN and osc < 72.0:
            strength = momentum + (fast / slow - 1.0)
            candidates.append((strength, symbol))
    candidates.sort(reverse=True)

    for _strength, symbol in candidates[:open_slots]:
        if len(orders) >= 14:
            break
        room = state.weight_room(symbol)
        want = int(state.equity * TARGET_WEIGHT)
        if symbol in WILD_NAMES or _recent_swing(symbol) > 0.16:
            want //= 2
        spend = min(want, room, state.cash)
        if spend < 2_000_000:
            continue
        impact = state.impact_bps(symbol, spend)
        if impact is not None and impact > 180:
            spend = spend // 2
            if spend < 2_000_000:
                continue
        orders.append({
            "side": "buy",
            "symbol": symbol,
            "notional_quote_units": spend,
            "max_slippage_bps": SLIPPAGE_BPS,
        })
        entry_close[symbol] = state.close(symbol)
        peak_close[symbol] = state.close(symbol)

    return orders


if __name__ == "__main__":
    makefun_bars.run(on_batch)
