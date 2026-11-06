"""Fine-tune YOLOv8 on RDD2022 India. Writes ml/models/road_damage/metrics.json.

Honesty: this script does not invent mAP. If Ultralytics or the dataset is missing
it exits with EXPERIMENTAL / evaluated=false. Classes stay D00/D10/D20/D40.

  python ml/scripts/train_rdd.py --data path/to/rdd_india.yaml --epochs 50

Evaluation protocol (see ml/models/road_damage/EVAL.md):
  * Promotion is decided on the VAL split only: the candidate's val mAP50 must reach the
    currently shipped weights' val mAP50 (re-measured now, on the same val images) plus
    --promote-margin.
  * The TEST split is evaluated once, on the promoted weights, after the decision. A rejected
    candidate is never scored on test. Test never influences promotion.
  * --field-data adds a never-trained-on hand-labelled windshield set as one more final number.
  * data.yaml 'path:' is rewritten to the real folder at run time (the yaml on disk stays as is).

Dataset: https://doi.org/10.6084/m9.figshare.21431547 (RDD2022 / CRDDC).
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `import eval_rdd` works from any cwd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "ml" / "models" / "road_damage"
METRICS = OUT_DIR / "metrics.json"
BACKEND_METRICS = ROOT / "backend" / "models" / "road_damage" / "metrics.json"
WEIGHTS = OUT_DIR / "YOLOv8_Small_RDD.pt"
INDIA_YAML = ROOT / "data" / "rdd_india" / "data.yaml"
INDIA_BEST = OUT_DIR / "YOLOv8s_RDD_india.pt"

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[assignment]

try:
    import eval_rdd
except ImportError:  # numpy missing: skip() below reports it like a missing ultralytics
    eval_rdd = None  # type: ignore[assignment]

CLASS_MAP = [
    {"id": "D00", "name": "Longitudinal crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D10", "name": "Transverse crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D20", "name": "Alligator crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D40", "name": "Pothole", "maps_to": "POTHOLE"},
]
MIN_TEST_IMAGES = 20


def write_metrics(payload: dict) -> None:
    text = json.dumps(payload, indent=2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(text, encoding="utf-8")
    BACKEND_METRICS.parent.mkdir(parents=True, exist_ok=True)
    BACKEND_METRICS.write_text(text, encoding="utf-8")
    print(f"wrote {METRICS}")


def _count_split(cfg: dict, split: str) -> int:
    try:
        return len(eval_rdd.split_images(cfg, split))
    except SystemExit:
        return 0


def _cuda() -> bool:
    return bool(torch is not None and torch.cuda.is_available())


def _split_info(cfg: dict) -> dict:
    """split_info.json written by prepare_rdd_india.py; {} for datasets built before it existed."""
    path = Path(str(cfg.get("path") or ".")) / "split_info.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _keep_awake() -> None:
    """Windows: ask the OS not to idle-sleep while this process runs (released when it exits). No settings change."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED


def skip(reason: str) -> int:
    write_metrics(
        {
            "honesty": "EXPERIMENTAL",
            "evaluated": False,
            "dataset": "RDD2022 India (CRDDC)",
            "note": reason,
            "classes": CLASS_MAP,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    print(reason, file=sys.stderr)
    return 2


# --------------------------------------------------------------------------------------
# Optional class-balanced sampling (replaces duplicating D10 image files on disk)
# --------------------------------------------------------------------------------------
def repeat_factor_weights(labels: list[dict], nc: int, thresh: float):
    """Per-image sampling weights by repeat-factor sampling (LVIS, Gupta et al. 2019).

    f_c = fraction of images containing class c; r_c = max(1, sqrt(thresh / f_c));
    an image's weight is the largest r_c among its classes (background images get 1).
    Rare classes are drawn more often per epoch without copying a single file.
    """
    import numpy as np

    present = np.zeros((len(labels), nc), dtype=bool)
    for i, lab in enumerate(labels):
        cls = np.asarray(lab["cls"]).reshape(-1).astype(int)
        present[i, cls[(cls >= 0) & (cls < nc)]] = True
    freq = present.mean(0)
    r_c = np.where(freq > 0, np.maximum(1.0, np.sqrt(thresh / np.maximum(freq, 1e-9))), 1.0)
    return np.where(present, r_c[None, :], 1.0).max(1)


def domain_weights(files: list[str], domain: dict[str, float]):
    """Per-image multiplier by filename prefix, e.g. {"India_": 2.0} draws India images twice as often."""
    import numpy as np

    names = [Path(f).name for f in files]
    return np.array([next((w for prefix, w in domain.items() if n.startswith(prefix)), 1.0) for n in names])


def make_balanced_trainer(thresh: float | None, domain: dict[str, float] | None = None):
    """DetectionTrainer whose train loader draws images with repeat-factor (thresh) and/or domain weights."""
    from torch.utils.data import WeightedRandomSampler
    from ultralytics.data.build import InfiniteDataLoader
    from ultralytics.models.yolo.detect import DetectionTrainer

    class BalancedTrainer(DetectionTrainer):
        def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
            loader = super().get_dataloader(dataset_path, batch_size, rank, mode)
            if mode != "train" or rank != -1:  # DDP keeps its DistributedSampler
                return loader
            ds = loader.dataset
            weights = repeat_factor_weights(ds.labels, int(self.data["nc"]), thresh) if thresh else torch.ones(len(ds)).numpy()
            if domain:
                weights = weights * domain_weights(ds.im_files, domain)
            print(f"[class-balanced] repeat-factor thresh={thresh}, domain={domain}: mean weight {weights.mean():.3f}, max {weights.max():.3f} over {len(weights)} images")
            sampler = WeightedRandomSampler(torch.as_tensor(weights, dtype=torch.double), num_samples=len(ds), replacement=True)
            return InfiniteDataLoader(
                dataset=ds,
                batch_size=loader.batch_size,
                shuffle=False,
                num_workers=loader.num_workers,
                sampler=sampler,
                prefetch_factor=loader.prefetch_factor,
                pin_memory=loader.pin_memory,
                collate_fn=loader.collate_fn,
                worker_init_fn=loader.worker_init_fn,
                generator=loader.generator,
                drop_last=loader.drop_last,
            )

    return BalancedTrainer


def _eval_summary(payload: dict, names: list[str]) -> dict:
    """map50 / map50_95 / per-class AP50 / CI out of an eval_rdd payload. model.val() numbers are the
    headline (same definition train_rdd.py always used); the CI comes from the bootstrap pipeline."""
    uv = payload.get("ultralytics_val") or {}
    own = payload["own"]
    ci = payload.get("bootstrap", {}).get("metrics", {})
    per = {}
    for name in names:
        value = (uv.get("per_class_ap50") or {}).get(name)
        per[name] = value if value is not None else own["per_class"][name]["ap50"]

    def span(key: str):
        entry = ci.get(key) or {}
        return [entry["lo"], entry["hi"]] if entry.get("lo") is not None else None

    return {
        "map50": uv.get("map50") if uv.get("map50") is not None else own["map50"],
        "map50_95": uv.get("map50_95") if uv.get("map50_95") is not None else own["map50_95"],
        "per_class_ap50": per,
        "ci95": {"map50": span("map50"), "map50_95": span("map50_95")},
        "operating_point": own["operating_point"],
        "n_images": payload["n_images"],
        "eval_json": None,
    }


def report_candidate(best: Path, data: Path, runtime_yaml: Path, cfg: dict, names: list[str], args: argparse.Namespace, device: str, n_test: int) -> int:
    """--no-promote: val (it picked best.pt, so it is a selection number) and test once, with CIs.

    Writes eval JSONs next to the weights and runs/<name>_candidate.json. The shipped weights and
    metrics.json stay as they are: shipping the candidate is a separate, deliberate step.
    """
    report: dict = {"candidate": str(best), "data": str(data), "split": _split_info(cfg), "at": datetime.now(timezone.utc).isoformat()}
    splits = ["val"] + (["test"] if not args.skip_test and n_test >= MIN_TEST_IMAGES else [])
    for split in splits:
        ctx = eval_rdd.make_ctx(data, split, imgsz=args.imgsz, device=device, prepared=(runtime_yaml, cfg))
        payloads, _ = eval_rdd.evaluate_many([best], ctx, boot=args.boot)
        out_json = eval_rdd.default_out(best, split)
        eval_rdd.write_json(out_json, payloads[0])
        eval_rdd.print_payload(payloads[0], names)
        report[split] = {**_eval_summary(payloads[0], names), "eval_json": str(out_json)}
        # PyTorch's allocator grows from one evaluation to the next (NMS at conf=0.001 asks for ~3 GB blocks, and on
        # Windows shared GPU memory lets it climb past 16 GB), so the second split ran out of memory in a fresh process.
        del ctx, payloads
        gc.collect()
        if _cuda():
            torch.cuda.empty_cache()
    out = OUT_DIR / "runs" / f"{args.name}_candidate.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"candidate report {out}. Shipped weights and metrics.json were not touched.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Honest RDD2022 India fine-tune")
    parser.add_argument("--data", help="Ultralytics data yaml (train/val + names D00 D10 D20 D40)")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--model", default=str(WEIGHTS) if WEIGHTS.is_file() else "yolov8s.pt")
    parser.add_argument("--device", default="")
    parser.add_argument("--eval-only", action="store_true", help="Do not train; gate and score --model (default: re-measure the shipped India weights)")
    parser.add_argument("--lr0", type=float, default=0.001)
    parser.add_argument("--optimizer", default="SGD", help="SGD keeps lr0. auto ignores it.")
    parser.add_argument("--freeze", type=int, default=10)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--save-period", type=int, default=-1, help="save a checkpoint every N epochs (-1 = only best and last)")
    parser.add_argument("--close-mosaic", type=int, default=15)
    parser.add_argument("--name", default="india_best")
    parser.add_argument(
        "--phone-aug",
        action="store_true",
        help="Stronger HSV/mixup. Do not use on a converged India checkpoint.",
    )
    parser.add_argument(
        "--note-extra",
        default="",
        help="Appended to metrics.json note (Hugging Face mix, extra countries, …).",
    )
    parser.add_argument("--promote-margin", type=float, default=0.0, help="candidate val mAP50 must beat the shipped weights' val mAP50 by this much")
    parser.add_argument("--skip-test", action="store_true", help="never touch the test split in this run")
    parser.add_argument("--boot", type=int, default=1000, help="bootstrap resamples for the final test CI (0 = off)")
    parser.add_argument("--field-data", help="data_field.yaml from prepare_rdd_india.py --field-test-dir; scored once at the end")
    parser.add_argument(
        "--class-balanced",
        action="store_true",
        help="repeat-factor sampler: rare classes (D10) drawn more often. Replaces duplicating D10 files on disk.",
    )
    parser.add_argument("--rfs-thresh", type=float, default=0.5, help="repeat-factor threshold; classes in fewer than this fraction of images are oversampled")
    parser.add_argument(
        "--domain-weight",
        action="append",
        default=[],
        metavar="PREFIX=W",
        help="draw train images whose filename starts with PREFIX W times as often (repeatable), e.g. India_=2 when India is a minority of a country mix",
    )
    parser.add_argument("--workers", type=int, default=2, help="train dataloader workers (val uses twice as many)")
    parser.add_argument("--cos-lr", action="store_true", help="cosine LR decay instead of linear")
    parser.add_argument("--cache", choices=("none", "ram", "disk"), default="none", help="Ultralytics image cache")
    parser.add_argument("--mixup", type=float, default=None, help="mixup probability (Ultralytics default when unset)")
    parser.add_argument("--warmup-epochs", type=float, default=None, help="Ultralytics default (3) when unset")
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="candidate report only: score the trained weights on val, then once on test; never touch the shipped weights or metrics.json",
    )
    args = parser.parse_args()
    try:
        domain = {k: float(v) for k, v in (item.split("=", 1) for item in args.domain_weight)}
    except ValueError:
        return skip(f"--domain-weight wants PREFIX=W, got {args.domain_weight}")
    if not args.data and INDIA_YAML.is_file():
        args.data = str(INDIA_YAML)
    if not args.data:
        return skip("No --data yaml. Run ml/scripts/prepare_rdd_india.py first. Do not quote sivakanth/oracl4 mAP as UrbanSense.")
    data = Path(args.data)
    if not data.is_file():
        return skip(f"data yaml missing: {data}")
    if YOLO is None:
        return skip("ultralytics is not installed. pip install ultralytics in the training env.")
    if eval_rdd is None:
        return skip("ml/scripts/eval_rdd.py could not be imported (numpy / pyyaml missing in this env).")

    device = args.device or ("0" if _cuda() else "cpu")
    runtime_yaml, cfg = eval_rdd.materialize_data_yaml(data)
    names = eval_rdd.class_names(cfg)
    n_test = _count_split(cfg, "test")
    info = _split_info(cfg)
    model = YOLO(args.model)
    best = Path(args.model)
    train_kw: dict = {
        "data": str(runtime_yaml),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "device": device,
        "batch": args.batch,
        "workers": args.workers,
        "patience": args.patience,
        "save_period": args.save_period,
        "optimizer": args.optimizer,
        "lr0": args.lr0,
        "lrf": 0.01,
        "freeze": args.freeze,
        # No-op: CopyPaste needs instance masks and returns immediately for box-only labels (see EVAL.md).
        "copy_paste": 0.2,
        "close_mosaic": args.close_mosaic,
        # Ultralytics 8.4 trains channels_last on CUDA by default; on the RTX 4060 box (torch 2.6 cu124)
        # that made YOLOv8m fwd+bwd 3.7x slower (12 vs 46 img/s at batch 8).
        "channels_last": False,
        "cos_lr": args.cos_lr,
        "cache": False if args.cache == "none" else args.cache,
        "project": str(OUT_DIR / "runs"),
        "name": args.name,
        "exist_ok": False,
    }
    if args.mixup is not None:
        train_kw["mixup"] = args.mixup
    if args.warmup_epochs is not None:
        train_kw["warmup_epochs"] = args.warmup_epochs
    if args.class_balanced or domain:
        train_kw["trainer"] = make_balanced_trainer(args.rfs_thresh if args.class_balanced else None, domain)
    if args.phone_aug:
        train_kw.update(
            hsv_h=0.015,
            hsv_s=0.5,
            hsv_v=0.4,
            degrees=4.0,
            translate=0.05,
            scale=0.15,
            mixup=0.05,
            erasing=0.15,
        )
    if not args.eval_only:
        _keep_awake()
        results = model.train(**train_kw)
        save_dir = Path(getattr(results, "save_dir", OUT_DIR / "runs" / args.name))
        best = save_dir / "weights" / "best.pt"
        # The trainer keeps model, optimizer and EMA on the GPU: let go of all of it before scoring in this process.
        model.trainer = None
        del model, results
        gc.collect()
        if _cuda():
            torch.cuda.empty_cache()
    elif INDIA_BEST.is_file() and not Path(args.model).is_file():
        best = INDIA_BEST
    if not best.is_file():
        return skip(f"no weights to evaluate at {best}")
    if args.no_promote:
        return report_candidate(best, data, runtime_yaml, cfg, names, args, device, n_test)

    # ---- 1. promotion gate: VAL only ----------------------------------------------------
    shipped = INDIA_BEST.resolve() if INDIA_BEST.is_file() else None
    final = INDIA_BEST  # whatever happens below, the weights that get the final numbers
    is_shipped = shipped is not None and best.resolve() == shipped
    val_kw = {"imgsz": args.imgsz, "device": device}
    promote_info: dict = {"split": "val", "margin": args.promote_margin}
    if not is_shipped:
        try:
            cand_val = eval_rdd.val_metrics(YOLO(str(best)), runtime_yaml, "val", names, **val_kw)
            inc_val = eval_rdd.val_metrics(YOLO(str(INDIA_BEST)), runtime_yaml, "val", names, **val_kw) if shipped else None
        except Exception as exc:
            return skip(f"Training finished but val failed: {exc}")
        floor = float(inc_val["map50"]) if inc_val else 0.0
        promoted = bool(cand_val["map50"] is not None and cand_val["map50"] + 1e-6 >= floor + args.promote_margin)
        promote_info.update(candidate_val_map50=cand_val["map50"], shipped_val_map50=inc_val["map50"] if inc_val else None, promoted=promoted)
        if not promoted:
            print(
                f"kept previous India weights. candidate val map50={cand_val['map50']} did not reach "
                f"shipped val map50={floor} + margin {args.promote_margin}. Test split was NOT evaluated.",
                file=sys.stderr,
            )
            gate = OUT_DIR / "runs" / f"{args.name}_gate.json"
            gate.parent.mkdir(parents=True, exist_ok=True)
            gate.write_text(json.dumps({**promote_info, "candidate": str(best), "at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
            return 0
        INDIA_BEST.write_bytes(best.read_bytes())
        print(f"promoted {best} on val: map50={cand_val['map50']} (shipped {floor}, margin {args.promote_margin}) -> {INDIA_BEST}")
    else:
        promote_info.update(promoted=None, note="re-measuring the shipped weights; no promotion decision")
        try:
            promote_info["candidate_val_map50"] = eval_rdd.val_metrics(YOLO(str(final)), runtime_yaml, "val", names, **val_kw)["map50"]
        except Exception as exc:
            return skip(f"val failed: {exc}")

    # ---- 2. final numbers: test evaluated ONCE on the promoted weights ------------------
    use_test = not args.skip_test and n_test >= MIN_TEST_IMAGES
    split_name = "test" if use_test else "val"
    ctx = eval_rdd.make_ctx(data, split_name, imgsz=args.imgsz, device=device, prepared=(runtime_yaml, cfg))
    try:
        payloads, _ = eval_rdd.evaluate_many([final], ctx, boot=args.boot)
    except Exception as exc:
        return skip(f"Promoted, but final {split_name} evaluation failed: {exc}")
    summary = _eval_summary(payloads[0], names)
    out_json = eval_rdd.default_out(final, split_name)
    eval_rdd.write_json(out_json, payloads[0])
    summary["eval_json"] = str(out_json)
    eval_rdd.print_payload(payloads[0], names)

    field_block = None
    if args.field_data and not args.skip_test:
        field_prep = eval_rdd.materialize_data_yaml(Path(args.field_data))
        field_ctx = eval_rdd.make_ctx(Path(args.field_data), "test", imgsz=args.imgsz, device=device, prepared=field_prep)
        field_payloads, _ = eval_rdd.evaluate_many([final], field_ctx, boot=args.boot)
        field_block = _eval_summary(field_payloads[0], names)
        field_out = eval_rdd.default_out(final, "field")
        eval_rdd.write_json(field_out, field_payloads[0])
        field_block["eval_json"] = str(field_out)
        eval_rdd.print_payload(field_payloads[0], names)

    classes = []
    for i, row in enumerate(CLASS_MAP):
        item = dict(row)
        if i < len(names) and summary["per_class_ap50"].get(names[i]) is not None:
            item["map50"] = summary["per_class_ap50"][names[i]]
        item["index"] = i
        classes.append(item)

    recipe = {
        "lr0": args.lr0,
        "freeze": args.freeze,
        "epochs": args.epochs,
        # None = dataset predates split_info.json (those builds duplicated D10 files 10x)
        "d10_train_repeat": info.get("d10_train_repeat"),
        "class_balanced": bool(args.class_balanced),
        "rfs_thresh": args.rfs_thresh if args.class_balanced else None,
    }
    held_out = split_name == "test"
    write_metrics(
        {
            "honesty": "REAL" if summary.get("map50") else "EXPERIMENTAL",
            "evaluated": bool(summary.get("map50")),
            "dataset": "RDD2022 India (CRDDC) — this host",
            "note": (
                (
                    f"Test evaluated once, on the promoted weights; promotion was decided on val. "
                    if held_out
                    else "NO untouched test split in this run: these numbers are on val, which also picked the best epoch. "
                )
                + f"Fine-tune lr0={args.lr0}, freeze={args.freeze}. "
                "Dataset is RDD2022 India (Delhi / Gurugram / Haryana). "
                "The base checkpoint (oracl4 YOLOv8_Small_RDD.pt) was already trained on RDD2022 Japan and India, "
                "so this is in-distribution accuracy, not a field estimate. "
                "Twitter/Reddit comments were not used — they are unlabeled. "
                "Not a certified field accuracy. Waterlogging and Indian signs were not trained. "
                "Do not quote a rival mAP as ours."
                + (f" {args.note_extra.strip()}" if args.note_extra.strip() else "")
            ),
            "map50": summary["map50"],
            "map50_95": summary["map50_95"],
            "ci95": summary["ci95"],
            "operating_point": summary["operating_point"],
            "eval_split": split_name,
            "eval_json": summary["eval_json"],
            "promotion": promote_info,
            **({"field_test": field_block} if field_block else {}),
            "split": {
                "train": _count_split(cfg, "train"),
                "val": _count_split(cfg, "val"),
                "test": n_test,
                "seed": info.get("seed", 42),
                "mode": info.get("mode", "random"),
                "group_size": info.get("group_size"),
                "embargo": info.get("embargo"),
                "keep": ["D00", "D10", "D20", "D40"],
            },
            "recipe": recipe,
            "weights": "ml/models/road_damage/YOLOv8s_RDD_india.pt",
            "classes": classes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
