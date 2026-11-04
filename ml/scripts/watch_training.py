"""Live view of a running train_rdd.py run: progress bar, val metrics per epoch, ETA, GPU.

  .\\.venv-train\\Scripts\\python.exe scripts\\watch_training.py
  .\\.venv-train\\Scripts\\python.exe scripts\\watch_training.py --name simsplit_v8m_coco --epochs 120 --patience 40

Read-only: it only reads the run's results.csv and the log. Ctrl-C closes the view, not the training.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANSI = re.compile(r"\x1b?\[[0-9;?]*[A-Za-z]")
PROGRESS = re.compile(r"\b\d+/\d+\s+[\d.]+G\s")


def clear() -> None:
    os.system("cls" if sys.platform == "win32" else "clear")


def last_progress(log: Path) -> str:
    try:
        with log.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 40000))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return "(log not found)"
    lines = [re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7e]", " ", ANSI.sub("", ln))).strip() for ln in re.split(r"[\r\n]+", tail)]
    if any(ln.startswith("EXIT") for ln in lines[-3:]):
        return next(ln for ln in reversed(lines) if ln.startswith("EXIT")) + "  (run ended: see the log)"
    for ln in reversed(lines):
        if PROGRESS.search(ln):
            return ln
    for ln in reversed(lines):
        if ln:
            return ln[:160]
    return "(waiting for output)"


def read_rows(csv_path: Path) -> list[dict]:
    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            return [{k.strip(): v.strip() for k, v in row.items()} for row in csv.DictReader(fh)]
    except OSError:
        return []


def gpu() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        util, used, total, temp = [x.strip() for x in out.split(",")]
        return f"GPU {util}% | {int(used) / 1024:.1f}/{int(total) / 1024:.1f} GB | {temp} C"
    except Exception:
        return "GPU n/a"


def hms(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="simsplit_v8m_coco")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--patience", type=int, default=40)
    ap.add_argument("--log", type=Path, default=None)
    ap.add_argument("--every", type=float, default=2.0, help="refresh seconds")
    ap.add_argument("--rows", type=int, default=15, help="epochs shown")
    args = ap.parse_args()
    run = ROOT / "ml" / "models" / "road_damage" / "runs" / args.name
    log = args.log or ROOT / "data" / f"{args.name}_train.log"
    key = "metrics/mAP50(B)"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        while True:
            rows = read_rows(run / "results.csv")
            lines = [f"{args.name}   {datetime.now():%Y-%m-%d %H:%M:%S}   {gpu()}", "", "now: " + last_progress(log), ""]
            if rows:
                times = [float(r["time"]) for r in rows]
                gaps = [b - a for a, b in zip([0.0] + times[:-1], times)]
                per = sum(gaps[-10:]) / len(gaps[-10:])
                done = len(rows)
                left = max(0, args.epochs - done)
                best = max(rows, key=lambda r: float(r[key]))
                since = done - int(float(best["epoch"]))
                lines += [
                    f"epochs done {done}/{args.epochs}   elapsed {hms(times[-1])}   {per / 60:.1f} min/epoch",
                    f"remaining at most {hms(left * per)}  ->  latest finish {datetime.now() + timedelta(seconds=left * per):%a %d %b %H:%M}"
                    f"  (+ ~5 min final scoring; early stop after {args.patience} epochs without a new best)",
                    f"best val mAP50 {float(best[key]):.4f} at epoch {best['epoch']}   epochs since best {since}/{args.patience}",
                    "",
                    f"{'ep':>4} {'mAP50':>7} {'mAP50-95':>9} {'P':>6} {'R':>6} {'box':>6} {'cls':>6} {'dfl':>6}",
                ]
                for r in rows[-args.rows:]:
                    mark = " *" if r["epoch"] == best["epoch"] else ""
                    lines.append(
                        f"{r['epoch']:>4} {float(r[key]):>7.4f} {float(r['metrics/mAP50-95(B)']):>9.4f} "
                        f"{float(r['metrics/precision(B)']):>6.3f} {float(r['metrics/recall(B)']):>6.3f} "
                        f"{float(r['train/box_loss']):>6.3f} {float(r['train/cls_loss']):>6.3f} {float(r['train/dfl_loss']):>6.3f}{mark}"
                    )
                lines += ["", "(* = best so far; val is India only, images no model trained on)   Ctrl-C closes this view, training keeps running"]
            else:
                lines.append("no finished epoch yet")
            clear()
            print("\n".join(lines), flush=True)
            time.sleep(args.every)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
