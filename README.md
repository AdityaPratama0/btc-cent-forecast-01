# BTC 4-hour forecast

`main.py` reads each `.in` file from `MAKEFUN_INPUT_DIR` (default `/input`) and writes a deterministic JSON forecast to `MAKEFUN_OUTPUT_DIR` (default `/output`). It uses only Python's standard library and is intended for Python 3.13.

The forecast starts at persistence, then applies a small, clipped mean-reversion adjustment over the previous four hours. The adjustment is scaled by the fraction of the last 60 one-minute closes that changed. This is a compact heuristic, not a fitted market model.

## Local checks

Run the isolated protocol and determinism checks with:

```sh
python3 verify.py /path/to/btc-cent-forecast-01-kit
```

The verifier checks the six practice input hashes from the kit manifest, invokes each case twice in separate network-disabled Python 3.13 containers, validates output shape and bounds, and measures program runtime separately from container startup.

The official kit keeps the scorer and reference answers server-side. Local practice/backtest results are not the official score, and the practice window is not a reliable estimate of final performance.
