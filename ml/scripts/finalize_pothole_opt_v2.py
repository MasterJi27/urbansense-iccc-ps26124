"""Wait for pothole_opt_v2 to finish, then score the candidates on all three splits.

Run in its own process while training runs:

  python ml/scripts/finalize_pothole_opt_v2.py --wait-pid 19864

It never touches production weights: the shipped checkpoint is copied into the experiment's eval
folder first, and every JSON/table is written under ml/models/road_damage/runs/pothole_opt_v2_eval/.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "ml" / "models" / "road_damage" / "runs" / "pothole_opt_v2"
EVAL = ROOT / "ml" / "models" / "road_damage" / "runs" / "pothole_opt_v2_eval"
WEIGHTS = EVAL / "weights"
META = ROOT / "ml" / "runs" / "sadhaksaarthi_optimization" / "pothole_opt_v2"
PY = ROOT / ".venv-train" / "Scripts" / "python.exe"

CANDIDATES = [
    ("shipped", ROOT / "ml" / "models" / "road_damage" / "YOLOv8s_RDD_india.pt"),
    ("v1_ep14", ROOT / "ml" / "models" / "road_damage" / "runs" / "pothole_ft_v1" / "weights" / "last.pt"),
    ("v2_best", RUN / "weights" / "best.pt"),
    ("v2_last", RUN / "weights" / "last.pt"),
]
SPLITS = [
    ("optv2_india_val", ROOT / "data" / "rdd_pothole_opt_v2" / "data_india_val.yaml", "val"),
    ("optv2_india_test", ROOT / "data" / "rdd_pothole_opt_v2" / "data.yaml", "test"),
    ("optv2_kent_holdout", ROOT / "data" / "rdd_pothole_opt_v2" / "data_kent_holdout.yaml", "test"),
]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def process_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, errors="replace")
    return str(pid) in out.stdout


def wait_for(pid: int) -> None:
    log(f"waiting for training pid {pid}")
    while process_alive(pid):
        time.sleep(60)
    log("training process exited")
    time.sleep(5)


def copy_candidates() -> None:
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    for label, src in CANDIDATES:
        if not src.is_file():
            raise SystemExit(f"missing candidate {label}: {src}")
        dest = WEIGHTS / f"{label}.pt"
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
            log(f"copied {label} -> {dest}")


def run_split(tag: str, data: Path, split: str) -> Path:
    out = WEIGHTS / f"eval_compare_{tag}.json"
    if out.is_file():
        log(f"{tag}: already scored, reusing {out}")
        return out
    cmd = [
        str(PY),
        "ml/scripts/eval_rdd.py",
        "--weights",
        *[str(WEIGHTS / f"{label}.pt") for label, _ in CANDIDATES],
        "--labels",
        *[label for label, _ in CANDIDATES],
        "--data",
        str(data),
        "--split",
        split,
        "--tag",
        tag,
        "--boot",
        "1000",
    ]
    log(" ".join(cmd))
    with (EVAL / f"{tag}.log").open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0 or not out.is_file():
        raise SystemExit(f"{tag} evaluation failed; see {EVAL / (tag + '.log')}")
    log(f"{tag}: wrote {out}")
    return out


def read_epochs() -> list[dict]:
    path = RUN / "results.csv"
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["epoch"] = int(row["epoch"])
            row["time"] = float(row["time"])
            for key in ("metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/precision(B)", "metrics/recall(B)"):
                row[key] = float(row[key])
            row["fitness"] = 0.1 * row["metrics/mAP50(B)"] + 0.9 * row["metrics/mAP50-95(B)"]
            rows.append(row)
    return rows


def fmt(value, digits: int = 4) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def summary_table(tag: str, path: Path, kent: bool) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data["models"]
    if kent:
        head = "| model | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |\n|---|---:|---:|---:|---:|---:|---:|"
        rows = [head]
        for label, _ in CANDIDATES:
            m = models[label]
            d = m["own"]["per_class"]["D40"]
            op = m["own"]["operating_point"]
            rows.append(
                f"| {label} | {fmt(d['ap50'])} | {fmt(d['ap50_95'])} | {fmt(d['precision'])} | "
                f"{fmt(d['recall'])} | {fmt(d['f1'])} | {fmt(op['conf'], 3)} |"
            )
        return "\n".join(rows)

    head = (
        "| model | mAP50 | mAP50-95 | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    rows = [head]
    for label, _ in CANDIDATES:
        m = models[label]
        own = m["own"]
        d = own["per_class"]["D40"]
        op = own["operating_point"]
        rows.append(
            f"| {label} | {fmt(own.get('map50'))} | {fmt(own.get('map50_95'))} | {fmt(d['ap50'])} | "
            f"{fmt(d['ap50_95'])} | {fmt(d['precision'])} | {fmt(d['recall'])} | {fmt(d['f1'])} | "
            f"{fmt(op['conf'], 3)} |"
        )
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-pid", type=int, default=0)
    args = ap.parse_args()

    EVAL.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    if args.wait_pid:
        wait_for(args.wait_pid)

    copy_candidates()
    paths = {}
    for tag, data, split in SPLITS:
        paths[tag] = run_split(tag, data, split)

    epochs = read_epochs()
    best = max(epochs, key=lambda r: r["fitness"]) if epochs else None
    total_min = (epochs[-1]["time"] / 60) if epochs else 0

    lines = [
        "# pothole_opt_v2 — final results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Run directory: `{RUN}`",
        f"Selection split: Kent D40 val (80 images / 117 boxes); the 70-photo Kent holdout was never used for selection.",
        "",
        "## Training",
        "",
        f"- Completed epochs: **{len(epochs)}** (configured 120, patience 30)",
        f"- Wall time in training: **{total_min:.1f} min**",
    ]
    if best:
        lines += [
            f"- Best fitness epoch: **{best['epoch']}** (mAP50 {best['metrics/mAP50(B)']:.4f}, mAP50-95 {best['metrics/mAP50-95(B)']:.4f})",
            f"- `best.pt` is selected on kent_val; `last.pt` is epoch {epochs[-1]['epoch']}.",
        ]
    lines += ["", "| epoch | mAP50 | mAP50-95 | D40 not available in results.csv | fitness |", "|---:|---:|---:|---|---:|"]
    for r in epochs:
        lines.append(f"| {r['epoch']} | {r['metrics/mAP50(B)']:.4f} | {r['metrics/mAP50-95(B)']:.4f} | — | {r['fitness']:.4f} |")

    lines += ["", "## India validation (322 images, not used for selection)", "", summary_table("optv2_india_val", paths["optv2_india_val"], False)]
    lines += ["", "## India test (322 images, scored once after selection)", "", summary_table("optv2_india_test", paths["optv2_india_test"], False)]
    lines += ["", "## Kent holdout (70 photos, 137 D40 boxes, never used for selection)", "", summary_table("optv2_kent_holdout", paths["optv2_kent_holdout"], True)]
    lines += [
        "",
        "## Read this carefully",
        "",
        "- India val/test overlap the base checkpoint's training data (the shipped model memorised them), so those columns are in-distribution, not field accuracy.",
        "- The Kent holdout is the only split here that no candidate trained on. It is UK phone photography, not Indian roads; it measures pothole appearance transfer, not field performance.",
        "- `v2_best` is selected on the 80-image Kent val; its Kent holdout score is therefore a fair second check, but the selection itself is noisy.",
        "- No production weight, backend file, ONNX model or threshold was changed.",
        "",
    ]
    out = META / "FINAL_RESULTS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
