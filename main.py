"""Offline 240-minute BTC forecast for make.fun's program/v1 sandbox."""

import json
import math
import os
from pathlib import Path


MIN_PRICE = 0.00001
MAX_PRICE = 9_999_999.99999


def forecast(prices):
    if not prices:
        raise ValueError("empty price series")
    if any(type(p) not in (int, float) or not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError("prices must be finite positive numbers")
    close = prices[-1]
    shift = 0.0
    if len(prices) > 240:
        freshness = sum(
            prices[i] != prices[i - 1]
            for i in range(len(prices) - 60, len(prices))
        ) / 60
        shift = max(-0.005, min(0.005, -0.05 * freshness * math.log(close / prices[-241])))
    return round(min(MAX_PRICE, max(MIN_PRICE, close * math.exp(shift))), 5)


def run():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(input_dir.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case.get("case") != path.stem:
            raise ValueError(f"case id does not match filename: {path.name}")
        if case.get("horizon_minutes") != 240:
            raise ValueError("expected a 240-minute horizon")
        markets = case["markets"]
        if len(markets) != 1 or markets[0]["id"] != "btc-usdc":
            raise ValueError("expected one btc-usdc market")
        result = {"forecasts": [{"case": path.stem, "price": forecast(markets[0]["prices"])}]}
        destination = output_dir / (path.stem + ".out")
        if destination.is_symlink():
            raise ValueError("output must be a regular file")
        destination.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
