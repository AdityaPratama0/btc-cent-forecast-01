"""Check protocol and determinism for the six official practice inputs."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parent
MAX_OUTPUT_BYTES = 1_048_576
APP_TIMEOUT_SECONDS = 8

SUPERVISOR = r"""
import subprocess
import sys
import time
started = time.perf_counter()
try:
    result = subprocess.run(["python3", "-I", "/bot/main.py"], timeout=8)
except subprocess.TimeoutExpired:
    print("VERIFY_PROGRAM_TIMEOUT", file=sys.stderr, flush=True)
    sys.exit(124)
elapsed = time.perf_counter() - started
print(f"VERIFY_PROGRAM_SECONDS={elapsed:.9f}", file=sys.stderr, flush=True)
sys.exit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
"""


def fail(message):
    raise RuntimeError(message)


def verify(kit):
    manifest = json.loads((kit / "kit.json").read_text(encoding="utf-8"))
    expected = {
        item["path"].split("/")[-1]: item
        for item in manifest["files"]
        if item["path"].startswith("input/p") and item["path"].endswith(".in")
    }
    required = {f"p{i:02d}.in" for i in range(6)}
    if set(expected) != required:
        fail(f"manifest does not list exactly the six practice cases: {sorted(expected)}")
    sources = sorted((kit / "input").glob("p*.in"))
    if {path.name for path in sources} != required:
        fail(f"kit does not contain exactly p00.in through p05.in: {[p.name for p in sources]}")

    for source in sources:
        record = expected[source.name]
        content = source.read_bytes()
        if len(content) != record["size"]:
            fail(f"{source.name}: size differs from official kit manifest")
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            fail(f"{source.name}: SHA-256 differs from official kit manifest")

    results = []
    with tempfile.TemporaryDirectory(prefix="btc-verify-") as scratch:
        base = Path(scratch)
        base.chmod(0o755)
        for source in sources:
            case_dir = base / source.stem
            case_dir.mkdir(mode=0o755)
            shutil.copyfile(source, case_dir / source.name)
            runs = []
            for repeat in range(2):
                output = base / f"{source.stem}-{repeat}"
                output.mkdir(mode=0o777)
                output.chmod(0o777)
                container_name = f"btc-verify-{os.getpid()}-{source.stem}-{repeat}"
                command = [
                    "docker", "run", "--rm", "--pull=never", "--network=none",
                    "--cpus=1", "--memory=1024m", "--memory-swap=1024m",
                    "--pids-limit=64", "--read-only", "--cap-drop=ALL",
                    "--security-opt=no-new-privileges", "--user", "65534:65534",
                    "--name", container_name,
                    "--mount", f"type=bind,src={ROOT / 'main.py'},dst=/bot/main.py,readonly",
                    "--mount", f"type=bind,src={case_dir},dst=/input,readonly",
                    "--mount", f"type=bind,src={output},dst=/output",
                    "python:3.13-slim", "python3", "-I", "-c", SUPERVISOR,
                ]
                started = time.perf_counter()
                try:
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired as exc:
                    subprocess.run(
                        ["docker", "rm", "-f", container_name],
                        capture_output=True, text=True, timeout=30,
                    )
                    fail(f"{source.stem} run {repeat}: Docker infrastructure exceeded 60 seconds: {exc}")
                host_elapsed = time.perf_counter() - started
                if completed.returncode:
                    fail(f"{source.stem} run {repeat}: exit {completed.returncode}: {completed.stderr}")
                marker = next(
                    (line for line in completed.stderr.splitlines()
                     if line.startswith("VERIFY_PROGRAM_SECONDS=")),
                    None,
                )
                if marker is None:
                    fail(f"{source.stem} run {repeat}: missing in-container runtime measurement")
                app_elapsed = float(marker.split("=", 1)[1])
                if app_elapsed > APP_TIMEOUT_SECONDS:
                    fail(f"{source.stem} run {repeat}: app took {app_elapsed:.6f}s, over 8 seconds")

                files = list(output.iterdir())
                if len(files) != 1 or files[0].name != source.stem + ".out":
                    fail(f"{source.stem} run {repeat}: expected exactly {source.stem}.out")
                path = files[0]
                if not path.is_file() or path.is_symlink():
                    fail(f"{source.stem} run {repeat}: output is not a regular file")
                if path.stat().st_size > MAX_OUTPUT_BYTES:
                    fail(f"{source.stem} run {repeat}: output exceeds 1 MiB")
                try:
                    raw = path.read_bytes()
                    obj = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    fail(f"{source.stem} run {repeat}: output is not UTF-8 JSON: {exc}")
                if type(obj) is not dict or set(obj) != {"forecasts"}:
                    fail(f"{source.stem} run {repeat}: invalid top-level output shape")
                rows = obj["forecasts"]
                if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
                    fail(f"{source.stem} run {repeat}: invalid forecasts list")
                row = rows[0]
                if set(row) != {"case", "price"} or row["case"] != source.stem:
                    fail(f"{source.stem} run {repeat}: invalid forecast row")
                price = row["price"]
                if type(price) not in (int, float) or not math.isfinite(price) or not 0 < price < 10_000_000:
                    fail(f"{source.stem} run {repeat}: price is outside the required bounds")
                runs.append({"bytes": raw, "price": price, "app_seconds": app_elapsed,
                             "host_seconds": host_elapsed})

            if runs[0]["bytes"] != runs[1]["bytes"]:
                fail(f"{source.stem}: output is nondeterministic")
            results.append({
                "case": source.stem,
                "price": runs[0]["price"],
                "max_app_seconds": round(max(run["app_seconds"] for run in runs), 6),
                "max_host_seconds_including_container": round(max(run["host_seconds"] for run in runs), 6),
            })

    print(json.dumps({
        "status": "LOCAL_PROTOCOL_PASS",
        "cases": len(results),
        "executions": 2 * len(results),
        "deterministic": True,
        "network": "none",
        "runtime": "Python 3.13",
        "official_input_hashes": "verified",
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    verify(parser.parse_args().kit.resolve())
