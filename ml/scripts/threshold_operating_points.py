"""True precision/recall/F1 vs confidence, and TP/FP/FN counts, for D40.

Why this exists: Ultralytics `model.val(conf=...)` filters detections before computing AP, and
its reported P/R are always at the internal F1-optimal point. Sweeping `conf` therefore changes
AP (truncation) but does not give P/R *at that confidence*. This script predicts once at a low
floor, matches to ground truth once, then counts TPs/FPs/FNs at every threshold.

  python ml/scripts/threshold_operating_points.py \
    --weights shipped.pt v1_ep14.pt v2_best.pt --labels shipped v1_ep14 v2_best \
    --data data/rdd_pothole_opt_v2/data_kent_holdout.yaml --split test \
    --tag kent --out ml/models/road_damage/runs/pothole_opt_v2_eval/operating_kent.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "scripts"))

import eval_rdd  # noqa: E402

D40 = 3


def counts_at(pooled, cls: int, conf: float) -> dict:
    confs, _imgs, tp = pooled.by_class[cls]
    keep = confs >= conf
    n_pred = int(keep.sum())
    n_tp = int(tp[keep, 0].sum())
    n_gt = int(pooled.gt_count[:, cls].sum())
    return {
        "n_gt": n_gt,
        "n_pred": n_pred,
        "tp": n_tp,
        "fp": n_pred - n_tp,
        "fn": n_gt - n_tp,
        "precision": n_tp / n_pred if n_pred else 0.0,
        "recall": n_tp / n_gt if n_gt else 0.0,
        "f1": 2 * n_tp / (2 * n_tp + (n_pred - n_tp) + (n_gt - n_tp)) if n_gt or n_pred else 0.0,
    }


def counts_micro(pooled, conf: float) -> dict:
    n_gt = int(pooled.gt_count.sum())
    n_pred = n_tp = 0
    for c in range(pooled.nc):
        confs, _imgs, tp = pooled.by_class[c]
        keep = confs >= conf
        n_pred += int(keep.sum())
        n_tp += int(tp[keep, 0].sum())
    return {
        "n_gt": n_gt,
        "n_pred": n_pred,
        "tp": n_tp,
        "fp": n_pred - n_tp,
        "fn": n_gt - n_tp,
        "precision": n_tp / n_pred if n_pred else 0.0,
        "recall": n_tp / n_gt if n_gt else 0.0,
        "f1": 2 * n_tp / (2 * n_tp + (n_pred - n_tp) + (n_gt - n_tp)) if n_gt or n_pred else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs="+", type=Path, required=True)
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="")
    ap.add_argument("--iou", type=float, default=0.6)
    ap.add_argument("--confs", nargs="+", type=float, default=[0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50])
    ap.add_argument("--threshold", type=float, default=0.30, help="deployment candidate highlighted in the table")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if len(args.weights) != len(args.labels):
        raise SystemExit("--weights and --labels must have the same length")

    ctx = eval_rdd.make_ctx(args.data, args.split, imgsz=args.imgsz, batch=args.batch,
                            device=args.device, conf=0.001, iou=args.iou)
    payload = {"schema": "operating_points/1", "data": str(args.data), "split": args.split,
               "tag": args.tag, "threshold_highlight": args.threshold, "models": {}}

    for weight, label in zip(args.weights, args.labels):
        col = eval_rdd.collect(weight, ctx, run_val=False)
        pooled = col.pooled
        rows = []
        for conf in args.confs:
            rows.append({"conf": conf, "d40": counts_at(pooled, D40, conf),
                         "micro": counts_micro(pooled, conf)})
        payload["models"][label] = {"weights": str(Path(weight).resolve()),
                                    "weights_sha256": col.sha256, "rows": rows}
        print(f"\n{label}")
        for r in rows:
            d = r["d40"]
            star = " <-" if abs(r["conf"] - args.threshold) < 1e-9 else ""
            print(f"  conf {r['conf']:.2f}  D40 P={d['precision']:.3f} R={d['recall']:.3f} "
                  f"F1={d['f1']:.3f}  TP={d['tp']} FP={d['fp']} FN={d['fn']}{star}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Operating points — {args.tag}",
        "",
        f"Data: `{args.data}`, split `{args.split}`. IoU 0.5 for TP matching, NMS IoU {args.iou}, "
        f"imgsz {args.imgsz}. Counts are exact, not interpolated.",
        "",
        "| model | conf | D40 TP | D40 FP | D40 FN | D40 P | D40 R | D40 F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, model in payload["models"].items():
        for r in model["rows"]:
            d = r["d40"]
            mark = " **" if abs(r["conf"] - args.threshold) < 1e-9 else ""
            lines.append(
                f"| {label}{mark} | {r['conf']:.2f} | {d['tp']} | {d['fp']} | {d['fn']} | "
                f"{d['precision']:.3f} | {d['recall']:.3f} | {d['f1']:.3f} |"
            )
    lines += [
        "",
        "** marks the deployment-threshold candidate. Choose the row that matches the product's "
        "precision/recall preference; do not copy the F1-optimal confidence from a small eval split.",
        "",
    ]
    args.out.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {args.out} and {args.out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
