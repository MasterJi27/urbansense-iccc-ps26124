"""Ultralytics confidence sweep (reference only). For real operating points use
`threshold_operating_points.py`.

Warning: Ultralytics filters detections at `conf` *before* building the AP curve, so the AP columns
here are NOT threshold-independent — they fall as `conf` rises. Only use this file to cross-check
the P/R that Ultralytics itself reports; use `threshold_operating_points.py` for exact TP/FP/FN and
true P/R/F1 at each threshold.

  python ml/scripts/threshold_sweep.py ^
    --weights shipped.pt v2_best.pt --labels shipped v2_best ^
    --data data/rdd_pothole_opt_v2/data_kent_holdout.yaml --split test ^
    --tag kent --out ml/models/road_damage/runs/pothole_opt_v2_eval/threshold_kent.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D40 = 3


def d40_index(box) -> int | None:
    classes = [int(c) for c in getattr(box, "ap_class_index", [])]
    return classes.index(D40) if D40 in classes else None


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
    ap.add_argument("--confs", nargs="+", type=float, default=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if len(args.weights) != len(args.labels):
        raise SystemExit("--weights and --labels must have the same length")

    from ultralytics import YOLO

    rows = []
    for weight, label in zip(args.weights, args.labels):
        model = YOLO(str(weight))
        for conf in args.confs:
            r = model.val(
                data=str(args.data), split=args.split, imgsz=args.imgsz, batch=args.batch,
                device=args.device, conf=conf, iou=args.iou, plots=False, verbose=False,
            )
            box = r.box
            i = d40_index(box)
            row = {
                "model": label,
                "conf": conf,
                "overall_map50": float(box.map50),
                "overall_map50_95": float(box.map),
                "d40_present": i is not None,
            }
            if i is not None:
                row.update(
                    d40_p=float(box.p[i]),
                    d40_r=float(box.r[i]),
                    d40_f1=float(box.f1[i]),
                    d40_ap50=float(box.ap50[i]),
                    d40_ap50_95=float(box.ap[i]),
                )
            rows.append(row)
            print(f"{label:12s} conf={conf:.2f}  D40 P={row.get('d40_p', float('nan')):.3f} "
                  f"R={row.get('d40_r', float('nan')):.3f} F1={row.get('d40_f1', float('nan')):.3f} "
                  f"AP50={row.get('d40_ap50', float('nan')):.3f}  mAP50={row['overall_map50']:.3f}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"schema": "threshold_sweep/1", "data": str(args.data), "split": args.split,
                                    "tag": args.tag, "rows": rows}, indent=2), encoding="utf-8")

    lines = [
        f"# Threshold sweep — {args.tag}",
        "",
        f"Data: `{args.data}`, split `{args.split}`. IoU {args.iou}, imgsz {args.imgsz}.",
        "AP here is built from detections above the sampled confidence, so it is NOT comparable to the",
        "headline AP and falls as confidence rises. Reference only; see `operating_*.md` for exact counts.",
        "",
        "| model | conf | D40 P | D40 R | D40 F1 | D40 AP50 | overall mAP50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['conf']:.2f} | {row.get('d40_p', float('nan')):.3f} | "
            f"{row.get('d40_r', float('nan')):.3f} | {row.get('d40_f1', float('nan')):.3f} | "
            f"{row.get('d40_ap50', float('nan')):.3f} | {row['overall_map50']:.3f} |"
        )
    args.out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} and {args.out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
