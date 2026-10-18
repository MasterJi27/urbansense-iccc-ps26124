"""Evaluate ANY YOLO .pt on a data.yaml split, with image-level bootstrap CIs.

Prints and writes: mAP50, mAP50-95, per-class AP50, precision / recall / F1 at the
F1-optimal confidence, and bootstrap 95% confidence intervals over images. The test
split is only a few hundred images, so differences under about 0.03 mAP are noise.
Pass several weights to also get a paired comparison table (first = reference).

  python scripts/eval_rdd.py --weights models/road_damage/YOLOv8s_RDD_india.pt --data .data/rdd_india/data.yaml
  python scripts/eval_rdd.py --weights base.pt tuned.pt --labels base tuned --data X/data.yaml --split test

Two numbers per model are reported side by side:
  ultralytics_val  model.val() — the number train_rdd.py has always printed.
  own              this script's own predict + greedy match + COCO-style AP (a port of
                   the Ultralytics metrics code), run on the same images. The bootstrap
                   needs per-image detections, which model.val() does not expose, so the
                   CI is computed on this pipeline. The two usually agree within ~0.005.

Output JSON goes next to the weights: <weights stem>_eval_<tag>.json (tag defaults to the
split). With several weights, eval_compare_<tag>.json / .md go next to the first one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
IOUV = np.linspace(0.5, 0.95, 10)
PX = np.linspace(0.0, 1.0, 1000)
EPS = 1e-16
_TRAPZ = getattr(np, "trapezoid", None) or np.trapz  # np.trapz is gone in newer numpy


# --------------------------------------------------------------------------------------
# data.yaml handling
# --------------------------------------------------------------------------------------
def _yaml():
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML is missing (pip install pyyaml; it ships with ultralytics).")
    return yaml


def _norm(p: object) -> str:
    return os.path.normcase(str(p).replace("\\", "/")).rstrip("/")


def materialize_data_yaml(data: Path) -> tuple[Path, dict]:
    """Return (yaml to hand to Ultralytics, parsed cfg) with 'path:' pointing at the real folder.

    The data.yaml files written on the training box hard-code D:/... paths. When the yaml
    sits next to an images/ folder (every prepare_*.py layout) that folder is the dataset
    root, so 'path:' is rewritten to it in a sibling <name>.runtime.yaml. The original file
    is never edited. Absolute split entries that do not exist are rebased onto images/<name>.
    """
    data = data.resolve()
    if not data.is_file():
        raise SystemExit(f"data yaml not found: {data}")
    cfg = _yaml().safe_load(data.read_text(encoding="utf-8")) or {}
    here = data.parent
    declared = cfg.get("path")
    changed = False
    if (here / "images").is_dir():
        real = here.as_posix()
        if declared is None or _norm(declared) != _norm(real):
            cfg["path"] = real
            changed = True
    elif declared is None:
        cfg["path"] = here.as_posix()
        changed = True
    root = Path(str(cfg["path"]))

    def rebase(entry):
        nonlocal changed
        if not isinstance(entry, str):
            return entry
        p = Path(entry)
        if p.is_absolute() and not p.exists():
            alt = root / "images" / p.name
            if alt.exists():
                changed = True
                return alt.as_posix()
        return entry

    for key in ("train", "val", "test"):
        value = cfg.get(key)
        if isinstance(value, list):
            cfg[key] = [rebase(v) for v in value]
        elif value:
            cfg[key] = rebase(value)
    if not changed:
        return data, cfg
    text = _yaml().safe_dump(cfg, sort_keys=False)
    target = data.with_name(f"{data.stem}.runtime.yaml")
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        target = Path(tempfile.mkdtemp(prefix="rdd_yaml_")) / "data.runtime.yaml"
        target.write_text(text, encoding="utf-8")
    print(f"[yaml] path: {declared!r} -> {cfg['path']!r}  (runtime copy {target}; original untouched)")
    return target, cfg


def class_names(cfg: dict) -> list[str]:
    names = cfg.get("names")
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names, key=lambda k: int(k))]
    return [str(n) for n in (names or [])]


def split_images(cfg: dict, split: str) -> list[Path]:
    entry = cfg.get(split)
    if not entry:
        raise SystemExit(f"data yaml has no '{split}' split (keys: {[k for k in ('train', 'val', 'test') if cfg.get(k)]})")
    root = Path(str(cfg.get("path") or "."))
    files: list[Path] = []
    for item in entry if isinstance(entry, list) else [entry]:
        p = Path(str(item))
        if not p.is_absolute():
            p = root / p
        if p.is_dir():
            files += [q for q in p.rglob("*") if q.suffix.lower() in IMG_EXT]
        elif p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                q = Path(line.replace("./", str(p.parent) + os.sep, 1) if line.startswith("./") else line)
                if q.suffix.lower() in IMG_EXT:
                    files.append(q)
        else:
            raise SystemExit(f"{split}: {p} does not exist")
    files = sorted(set(files))
    if not files:
        raise SystemExit(f"{split}: no images found under {entry}")
    return files


def label_for(img: Path) -> Path:
    """Ultralytics convention: .../images/x.jpg -> .../labels/x.txt (last 'images' only)."""
    a, b = f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}"
    s = str(img)
    head, sep, tail = s.rpartition(a)
    s = head + b + tail if sep else s
    return Path(s).with_suffix(".txt")


def load_gt(label: Path, w: int, h: int, nc: int) -> tuple[np.ndarray, np.ndarray]:
    """Ground truth as (classes (n,), xyxy pixels (n,4)). Missing/empty label file = background."""
    if not label.is_file():
        return np.zeros(0, dtype=int), np.zeros((0, 4))
    rows = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls = float(parts[0])
        if len(parts) == 5:
            xc, yc, bw, bh = (float(v) for v in parts[1:5])
        else:  # segment polygon -> its bounding box
            pts = np.array([float(v) for v in parts[1:]]).reshape(-1, 2)
            (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
            xc, yc, bw, bh = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        rows.append([cls, xc, yc, bw, bh])
    if not rows:
        return np.zeros(0, dtype=int), np.zeros((0, 4))
    arr = np.unique(np.array(rows), axis=0)  # Ultralytics drops duplicate label rows too
    cls = arr[:, 0].astype(int)
    if cls.min() < 0 or cls.max() >= nc:
        raise SystemExit(f"{label}: class id outside 0..{nc - 1}")
    xyxy = np.stack(
        [(arr[:, 1] - arr[:, 3] / 2) * w, (arr[:, 2] - arr[:, 4] / 2) * h, (arr[:, 1] + arr[:, 3] / 2) * w, (arr[:, 2] + arr[:, 4] / 2) * h],
        axis=1,
    )
    return cls, xyxy


# --------------------------------------------------------------------------------------
# Matching and AP (numpy port of the Ultralytics metrics code)
# --------------------------------------------------------------------------------------
def box_iou_np(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU matrix (len(a), len(b)) for xyxy boxes."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.clip(rb - lt, 0, None).prod(2)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-7)


def match_greedy(pred_cls: np.ndarray, gt_cls: np.ndarray, iou: np.ndarray) -> np.ndarray:
    """(n_pred, 10) bool: is each prediction a TP at IoU 0.50:0.95. Predictions must be sorted by
    descending confidence. Same-class, one-to-one, each detection claims its best unclaimed target."""
    n = len(pred_cls)
    correct = np.zeros((n, len(IOUV)), dtype=bool)
    if n == 0 or len(gt_cls) == 0:
        return correct
    iou = iou * (gt_cls[:, None] == pred_cls[None, :])
    matched = np.zeros((iou.shape[0], len(IOUV)), dtype=bool)
    cols = np.arange(len(IOUV))
    for j in np.flatnonzero((iou >= IOUV.min()).any(0)):
        available = np.where(matched, 0.0, iou[:, j, None])
        k = available.argmax(0)
        ok = available[k, cols] >= IOUV
        correct[j] = ok
        matched[k, cols] |= ok
    return correct


def compute_ap(recall: np.ndarray, precision: np.ndarray) -> float:
    mrec = np.concatenate(([0.0], recall, [recall[-1] if len(recall) else 1.0], [1.0]))
    mpre = np.concatenate(([1.0], precision, [0.0], [0.0]))
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    x = np.linspace(0, 1, 101)  # 101-point interpolation (COCO)
    return float(_TRAPZ(np.interp(x, mrec, mpre), x))


def smooth(y: np.ndarray, f: float = 0.05) -> np.ndarray:
    nf = round(len(y) * f * 2) // 2 + 1
    p = np.ones(nf // 2)
    yp = np.concatenate((p * y[0], y, p * y[-1]), 0)
    return np.convolve(yp, np.ones(nf) / nf, mode="valid")


class Pooled:
    """All detections / ground truth of a split, pre-sorted per class so bootstrap resamples are cheap."""

    def __init__(self, per_image: list[dict], nc: int):
        self.nc = nc
        self.n_images = len(per_image)
        self.gt_count = np.zeros((self.n_images, nc))
        conf, cls, img, tp = [], [], [], []
        for i, s in enumerate(per_image):
            self.gt_count[i] = np.bincount(s["gt_cls"], minlength=nc)[:nc]
            conf.append(s["conf"])
            cls.append(s["cls"])
            img.append(np.full(len(s["conf"]), i))
            tp.append(s["tp"])
        conf = np.concatenate(conf) if conf else np.zeros(0)
        cls = np.concatenate(cls) if cls else np.zeros(0, dtype=int)
        img = np.concatenate(img) if img else np.zeros(0, dtype=int)
        tp = np.concatenate(tp) if tp else np.zeros((0, len(IOUV)), dtype=bool)
        self.by_class = []
        for c in range(nc):
            m = np.flatnonzero(cls == c)
            order = m[np.argsort(-conf[m], kind="stable")]
            self.by_class.append((conf[order], img[order], tp[order].astype(float)))
        self.n_det = int(len(conf))


def compute_metrics(pooled: Pooled, w: np.ndarray | None = None, op_idx: int | None = None) -> dict:
    """AP per class/IoU plus P/R/F1 at the F1-optimal confidence.

    w = per-image multiplicities (bootstrap resample as weights); None = every image once.
    op_idx = index into PX of the operating point to use; None = pick the F1-optimal one
    (argmax of the 0.1-smoothed mean-over-classes F1 curve, exactly as Ultralytics does).
    Classes with no ground truth in the (re)sample are NaN and excluded from the means.
    """
    nc = pooled.nc
    ap = np.full((nc, len(IOUV)), np.nan)
    p_curve = np.zeros((nc, len(PX)))
    r_curve = np.zeros((nc, len(PX)))
    n_gt = pooled.gt_count.sum(0) if w is None else w @ pooled.gt_count
    for c in range(nc):
        n_l = n_gt[c]
        if n_l <= 0:
            continue
        conf, img, tp = pooled.by_class[c]
        if w is not None:
            wc = w[img]
            keep = wc > 0
            conf, tp, wc = conf[keep], tp[keep], wc[keep]
        if len(conf) == 0:
            ap[c] = 0.0
            continue
        if w is None:
            tpc, fpc = tp.cumsum(0), (1 - tp).cumsum(0)
        else:
            tpc, fpc = (tp * wc[:, None]).cumsum(0), ((1 - tp) * wc[:, None]).cumsum(0)
        recall = tpc / (n_l + EPS)
        precision = tpc / (tpc + fpc)
        r_curve[c] = np.interp(-PX, -conf, recall[:, 0], left=0)
        p_curve[c] = np.interp(-PX, -conf, precision[:, 0], left=1)
        for j in range(len(IOUV)):
            ap[c, j] = compute_ap(recall[:, j], precision[:, j])
    present = n_gt > 0
    f1_curve = 2 * p_curve * r_curve / (p_curve + r_curve + EPS)
    if op_idx is None:
        op_idx = int(smooth(f1_curve[present].mean(0), 0.1).argmax()) if present.any() else 0
    p, r, f1 = p_curve[:, op_idx].copy(), r_curve[:, op_idx].copy(), f1_curve[:, op_idx].copy()
    for arr in (p, r, f1):
        arr[~present] = np.nan
    return {
        "ap": ap,
        "present": present,
        "n_gt": n_gt,
        "op_idx": op_idx,
        "conf": float(PX[op_idx]),
        "p": p,
        "r": r,
        "f1": f1,
    }


def _nanmean(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    return float(a.mean()) if len(a) else float("nan")


def flatten(m: dict, names: list[str]) -> dict[str, float]:
    ap = m["ap"]
    out = {
        "map50": _nanmean(ap[:, 0]),
        "map50_95": float(ap[m["present"]].mean()) if m["present"].any() else float("nan"),
        "precision": _nanmean(m["p"]),
        "recall": _nanmean(m["r"]),
        "f1": _nanmean(m["f1"]),
    }
    for c, name in enumerate(names):
        out[f"ap50/{name}"] = float(ap[c, 0])
        out[f"ap50_95/{name}"] = float(ap[c].mean()) if m["present"][c] else float("nan")
        out[f"precision/{name}"] = float(m["p"][c])
        out[f"recall/{name}"] = float(m["r"][c])
        out[f"f1/{name}"] = float(m["f1"][c])
    return out


# --------------------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------------------
def bootstrap_samples(pooled: list[Pooled], ops: list[int], names: list[str], boot: int, seed: int) -> list[dict[str, np.ndarray]]:
    """Resample images with replacement `boot` times. Every model sees the SAME resamples, so
    differences between models are paired. Returns, per model, {metric: array(boot)}."""
    n = pooled[0].n_images
    rng = np.random.default_rng(seed)
    acc: list[dict[str, list[float]]] = [{} for _ in pooled]
    for b in range(boot):
        w = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        for k, pk in enumerate(pooled):
            for key, value in flatten(compute_metrics(pk, w, ops[k]), names).items():
                acc[k].setdefault(key, []).append(value)
        if (b + 1) % 100 == 0 or b + 1 == boot:
            print(f"  bootstrap {b + 1}/{boot}", flush=True)
    return [{k: np.array(v) for k, v in d.items()} for d in acc]


def interval(samples: np.ndarray, point: float, level: float) -> dict:
    valid = samples[~np.isnan(samples)]
    if len(valid) < max(10, 0.5 * len(samples)):
        return {"point": _r(point), "lo": None, "hi": None, "se": None, "n_valid": int(len(valid))}
    lo, hi = np.percentile(valid, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return {"point": _r(point), "lo": _r(lo), "hi": _r(hi), "se": _r(valid.std(ddof=1)), "n_valid": int(len(valid))}


def _r(x: float | None, nd: int = 4) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


# --------------------------------------------------------------------------------------
# Running a model
# --------------------------------------------------------------------------------------
@dataclass
class Ctx:
    data: Path
    runtime_yaml: Path
    cfg: dict
    split: str
    images: list[Path]
    names: list[str]
    imgsz: int = 640
    batch: int = 16
    device: str = ""
    conf: float = 0.001
    iou: float = 0.6
    max_det: int = 300
    extra: dict = field(default_factory=dict)


def make_ctx(data: Path, split: str, *, imgsz: int = 640, batch: int = 16, device: str = "", conf: float = 0.001, iou: float = 0.6, max_det: int = 300, limit: int = 0, prepared: tuple[Path, dict] | None = None) -> Ctx:
    runtime, cfg = prepared or materialize_data_yaml(Path(data))
    names = class_names(cfg)
    if not names:
        raise SystemExit("data yaml has no 'names'")
    images = split_images(cfg, split)
    if limit and limit < len(images):
        images = images[:limit]
    return Ctx(Path(data), runtime, cfg, split, images, names, imgsz, batch, device or default_device(), conf, iou, max_det)


def default_device() -> str:
    try:
        import torch

        return "0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yolo(weights: Path):
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics is not installed. Run this in the training env (.venv-train).")
    return YOLO(str(weights))


def check_model_classes(model, ctx: Ctx, weights: Path) -> None:
    mnames = [str(model.names[i]) for i in sorted(model.names)]
    if len(mnames) != len(ctx.names):
        raise SystemExit(f"{weights.name} has {len(mnames)} classes {mnames} but the yaml has {len(ctx.names)} {ctx.names}")
    if [n.lower() for n in mnames] != [n.lower() for n in ctx.names]:
        print(f"[warn] {weights.name} class names {mnames} differ from yaml {ctx.names}; assuming the SAME index order.")


def val_metrics(model, data_yaml: Path, split: str, names: list[str], *, imgsz: int = 640, batch: int = 16, device: str = "", conf: float = 0.001, iou: float = 0.6, max_det: int = 300) -> dict:
    """The classic model.val() numbers (what train_rdd.py has always reported). No bootstrap, fast."""
    out_dir = tempfile.mkdtemp(prefix="rdd_val_")
    ev = model.val(
        data=str(data_yaml),
        split=split,
        imgsz=imgsz,
        batch=batch,
        conf=conf,
        iou=iou,
        max_det=max_det,
        device=device or default_device(),
        plots=False,
        verbose=False,
        project=out_dir,
        name="val",
        exist_ok=True,
    )
    box = ev.box
    per = {}
    idx = list(getattr(box, "ap_class_index", []))
    ap50 = list(getattr(box, "ap50", []))
    for i, cls in enumerate(idx):
        if i < len(ap50) and int(cls) < len(names):
            per[names[int(cls)]] = _r(float(ap50[i]))
    return {"map50": _r(float(box.map50)), "map50_95": _r(float(box.map)), "per_class_ap50": per}


def ultralytics_val(model, ctx: Ctx) -> dict:
    return val_metrics(model, ctx.runtime_yaml, ctx.split, ctx.names, imgsz=ctx.imgsz, batch=ctx.batch, device=ctx.device, conf=ctx.conf, iou=ctx.iou, max_det=ctx.max_det)


def collect_detections(model, ctx: Ctx) -> list[dict]:
    """Predict every image at low conf and match to ground truth -> per-image stats."""
    nc = len(ctx.names)
    sources = [str(p) for p in ctx.images]
    out: list[dict] = []
    stream = model.predict(
        source=sources,
        stream=True,
        imgsz=ctx.imgsz,
        conf=ctx.conf,
        iou=ctx.iou,
        max_det=ctx.max_det,
        device=ctx.device,
        batch=ctx.batch,
        half=False,
        verbose=False,
    )
    for i, r in enumerate(stream):
        h, w = r.orig_shape
        gt_cls, gt_xyxy = load_gt(label_for(Path(sources[i])), w, h, nc)
        boxes = r.boxes
        conf = boxes.conf.cpu().numpy().astype(float)
        cls = boxes.cls.cpu().numpy().astype(int)
        xyxy = boxes.xyxy.cpu().numpy().astype(float)
        order = np.argsort(-conf, kind="stable")
        conf, cls, xyxy = conf[order], cls[order], xyxy[order]
        tp = match_greedy(cls, gt_cls, box_iou_np(gt_xyxy, xyxy))
        out.append({"conf": conf, "cls": cls, "tp": tp, "gt_cls": gt_cls})
        if (i + 1) % 100 == 0:
            print(f"  predicted {i + 1}/{len(sources)}", flush=True)
    if len(out) != len(sources):
        raise SystemExit(f"predicted {len(out)} of {len(sources)} images; some could not be read")
    return out


@dataclass
class Collected:
    weights: Path
    sha256: str
    pooled: Pooled
    full: dict
    uv: dict | None


def collect(weights: Path, ctx: Ctx, run_val: bool = True) -> Collected:
    weights = Path(weights).resolve()
    if not weights.is_file():
        raise SystemExit(f"weights not found: {weights}")
    print(f"[{weights.name}] {len(ctx.images)} {ctx.split} images, classes {ctx.names}")
    model = load_yolo(weights)
    check_model_classes(model, ctx, weights)
    uv = None
    if run_val:
        print(f"[{weights.name}] model.val() ...", flush=True)
        uv = ultralytics_val(model, ctx)
    print(f"[{weights.name}] predict + match ...", flush=True)
    pooled = Pooled(collect_detections(model, ctx), len(ctx.names))
    return Collected(weights, sha256_of(weights), pooled, compute_metrics(pooled), uv)


def build_payload(col: Collected, ctx: Ctx, ci: dict[str, dict] | None, args_meta: dict) -> dict:
    full = col.full
    flat = flatten(full, ctx.names)
    per_class = {}
    for c, name in enumerate(ctx.names):
        per_class[name] = {
            "n_gt": int(full["n_gt"][c]),
            "ap50": _r(flat[f"ap50/{name}"]),
            "ap50_95": _r(flat[f"ap50_95/{name}"]),
            "precision": _r(flat[f"precision/{name}"]),
            "recall": _r(flat[f"recall/{name}"]),
            "f1": _r(flat[f"f1/{name}"]),
        }
    payload = {
        "schema": "eval_rdd/1",
        "weights": str(col.weights),
        "weights_sha256": col.sha256,
        "data": str(ctx.data),
        "split": ctx.split,
        "n_images": len(ctx.images),
        "n_detections_conf_floor": col.pooled.n_det,
        "settings": {"imgsz": ctx.imgsz, "conf": ctx.conf, "iou": ctx.iou, "max_det": ctx.max_det, **args_meta},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "ultralytics_val": col.uv,
        "own": {
            "map50": _r(flat["map50"]),
            "map50_95": _r(flat["map50_95"]),
            "per_class": per_class,
            "operating_point": {
                "note": "confidence that maximises the (0.1-smoothed) class-mean F1 on THIS split; optimistic by construction",
                "conf": _r(full["conf"]),
                "precision": _r(flat["precision"]),
                "recall": _r(flat["recall"]),
                "f1": _r(flat["f1"]),
            },
        },
    }
    if col.uv and col.uv.get("map50") is not None and flat["map50"] == flat["map50"]:
        gap = abs(flat["map50"] - col.uv["map50"])
        payload["agreement"] = {"map50_abs_diff_own_vs_ultralytics": _r(gap), "ok": gap <= 0.01}
    if ci is not None:
        payload["bootstrap"] = {"level": args_meta.get("ci_level"), "n": args_meta.get("boot"), "seed": args_meta.get("seed"), "method": "image-level bootstrap, percentile interval, multiplicity weights", "metrics": ci}
    return payload


def evaluate_many(weights: list[Path], ctx: Ctx, *, boot: int = 1000, seed: int = 42, level: float = 0.95, run_val: bool = True, labels: list[str] | None = None) -> tuple[list[dict], dict | None]:
    """Evaluate each weights file on ctx; returns (one payload per weights, comparison or None)."""
    cols = [collect(Path(w), ctx, run_val=run_val) for w in weights]
    cis: list[dict[str, dict] | None] = [None] * len(cols)
    deltas = None
    if boot > 0:
        print(f"bootstrap: {boot} resamples over {len(ctx.images)} images, seed {seed}")
        samples = bootstrap_samples([c.pooled for c in cols], [c.full["op_idx"] for c in cols], ctx.names, boot, seed)
        points = [flatten(c.full, ctx.names) for c in cols]
        cis = [{k: interval(s[k], points[i][k], level) for k in s} for i, s in enumerate(samples)]
        if len(cols) > 1:
            deltas = {}
            for i in range(1, len(cols)):
                label = (labels[i] if labels and i < len(labels) else cols[i].weights.stem)
                deltas[label] = {k: interval(samples[i][k] - samples[0][k], points[i][k] - points[0][k], level) for k in samples[i]}
    meta = {"boot": boot, "seed": seed, "ci_level": level}
    payloads = [build_payload(c, ctx, cis[i], meta) for i, c in enumerate(cols)]
    comparison = None
    if len(cols) > 1:
        comparison = {
            "schema": "eval_rdd_compare/1",
            "split": ctx.split,
            "n_images": len(ctx.images),
            "reference": labels[0] if labels else cols[0].weights.stem,
            "models": {(labels[i] if labels and i < len(labels) else c.weights.stem): payloads[i] for i, c in enumerate(cols)},
            "paired_delta_vs_reference": deltas,
        }
    return payloads, comparison


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------
def _fmt(entry: dict | None, nd: int = 3) -> str:
    if not entry or entry.get("point") is None:
        return "n/a"
    s = f"{entry['point']:.{nd}f}"
    if entry.get("lo") is not None:
        s += f" [{entry['lo']:.{nd}f}, {entry['hi']:.{nd}f}]"
    return s


def _fmt_delta(entry: dict | None, nd: int = 3) -> str:
    if not entry or entry.get("point") is None:
        return "n/a"
    s = f"{entry['point']:+.{nd}f}"
    if entry.get("lo") is None:
        return s
    s += f" [{entry['lo']:+.{nd}f}, {entry['hi']:+.{nd}f}]"
    return s + (" *" if entry["lo"] > 0 or entry["hi"] < 0 else " n.s.")


def metric_keys(names: list[str]) -> list[tuple[str, str]]:
    keys = [("map50", "mAP50"), ("map50_95", "mAP50-95")]
    keys += [(f"ap50/{n}", f"AP50 {n}") for n in names]
    keys += [("precision", "Precision @F1-opt conf"), ("recall", "Recall @F1-opt conf"), ("f1", "F1 @F1-opt conf")]
    return keys


def comparison_table(comparison: dict, names: list[str]) -> str:
    labels = list(comparison["models"])
    ref = labels[0]
    lines = [
        f"Split `{comparison['split']}`, {comparison['n_images']} images. Cells: point estimate [95% bootstrap CI over images].",
        "Delta columns are PAIRED (same resamples). `*` = CI excludes 0, `n.s.` = indistinguishable from noise.",
        "",
        "| metric | " + " | ".join(labels) + " | " + " | ".join(f"Δ {lab} − {ref}" for lab in labels[1:]) + " |",
        "|---|" + "---|" * (len(labels) + len(labels) - 1),
    ]
    for key, title in metric_keys(names):
        cells = [_fmt(comparison["models"][lab].get("bootstrap", {}).get("metrics", {}).get(key)) for lab in labels]
        dcells = [_fmt_delta(comparison["paired_delta_vs_reference"].get(lab, {}).get(key)) for lab in labels[1:]]
        lines.append(f"| {title} | " + " | ".join(cells) + " | " + " | ".join(dcells) + " |")
    ops = ", ".join(f"{lab}: conf {comparison['models'][lab]['own']['operating_point']['conf']}" for lab in labels)
    lines += ["", f"Operating points (F1-optimal on this split, so P/R/F1 are optimistic): {ops}."]
    return "\n".join(lines)


def print_payload(p: dict, names: list[str]) -> None:
    own, uv = p["own"], p.get("ultralytics_val")
    ci = p.get("bootstrap", {}).get("metrics", {})
    print(f"\n=== {Path(p['weights']).name}  [{p['split']}, {p['n_images']} images] ===")
    if uv:
        print(f"model.val():   mAP50 {uv['map50']}  mAP50-95 {uv['map50_95']}  per-class AP50 {uv['per_class_ap50']}")
    print(f"own pipeline:  mAP50 {_fmt(ci.get('map50')) if ci else own['map50']}  mAP50-95 {_fmt(ci.get('map50_95')) if ci else own['map50_95']}")
    if "agreement" in p and not p["agreement"]["ok"]:
        print(f"[warn] own vs model.val() mAP50 differ by {p['agreement']['map50_abs_diff_own_vs_ultralytics']} (>0.01). Trust model.val() for the headline; check the bootstrap pipeline.")
    for name in names:
        row = own["per_class"][name]
        print(f"  {name}: n_gt={row['n_gt']:>5}  AP50 {_fmt(ci.get(f'ap50/{name}')) if ci else row['ap50']}  P {row['precision']}  R {row['recall']}  F1 {row['f1']}")
        if row["n_gt"] and row["n_gt"] < 30:
            print(f"      [warn] only {row['n_gt']} {name} instances: this class's CI is very wide")
    op = own["operating_point"]
    print(f"  @F1-optimal conf {op['conf']}: P {_fmt(ci.get('precision')) if ci else op['precision']}  R {_fmt(ci.get('recall')) if ci else op['recall']}  F1 {_fmt(ci.get('f1')) if ci else op['f1']}")
    if ci and ci.get("map50", {}).get("lo") is not None:
        half = (ci["map50"]["hi"] - ci["map50"]["lo"]) / 2
        print(f"  mAP50 95% CI half-width ±{half:.3f}: differences smaller than this are noise.")


def write_json(path: Path, payload: dict) -> None:
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return None if math.isnan(float(o)) else float(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return o

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(payload), indent=2), encoding="utf-8")
    print(f"wrote {path}")


def default_out(weights: Path, split: str) -> Path:
    return Path(weights).resolve().with_name(f"{Path(weights).stem}_eval_{split}.json")


# --------------------------------------------------------------------------------------
# Self-test (numpy only: no torch, no weights, no data)
# --------------------------------------------------------------------------------------
def _synthetic(rng: np.random.Generator, n_images: int, noise: float, fp_rate: float, nc: int = 4) -> list[dict]:
    per_image = []
    for _ in range(n_images):
        k = rng.integers(0, 4)
        gt_cls = rng.integers(0, nc, k)
        xy = rng.uniform(0, 500, (k, 2))
        gt = np.concatenate([xy, xy + rng.uniform(30, 120, (k, 2))], axis=1)
        keep = rng.random(k) > noise  # missed detections
        pred = gt[keep] + rng.normal(0, 3 * noise * 10, (int(keep.sum()), 4))
        pcls = gt_cls[keep]
        pconf = rng.uniform(0.4, 1.0, len(pcls))
        n_fp = rng.poisson(fp_rate)
        fxy = rng.uniform(0, 500, (n_fp, 2))
        pred = np.concatenate([pred, np.concatenate([fxy, fxy + rng.uniform(30, 120, (n_fp, 2))], axis=1)])
        pcls = np.concatenate([pcls, rng.integers(0, nc, n_fp)])
        pconf = np.concatenate([pconf, rng.uniform(0.0, 0.5, n_fp)])
        order = np.argsort(-pconf)
        pred, pcls, pconf = pred[order], pcls[order], pconf[order]
        per_image.append({"conf": pconf, "cls": pcls, "tp": match_greedy(pcls, gt_cls, box_iou_np(gt, pred)), "gt_cls": gt_cls})
    return per_image


def selftest() -> int:
    names = ["D00", "D10", "D20", "D40"]
    rng = np.random.default_rng(0)
    perfect = Pooled(_synthetic(rng, 120, noise=0.0, fp_rate=0.0), 4)
    m = compute_metrics(perfect)
    # 0.995, not 1.0: the Ultralytics 101-point AP never quite reaches 1 because of its end sentinels
    assert abs(_nanmean(m["ap"][:, 0]) - 0.995) < 1e-3, "perfect detections must give AP50 = 0.995"
    empty = Pooled([{"conf": np.zeros(0), "cls": np.zeros(0, dtype=int), "tp": np.zeros((0, 10), dtype=bool), "gt_cls": np.array([0, 1])} for _ in range(5)], 4)
    assert _nanmean(compute_metrics(empty)["ap"][:, 0]) == 0.0, "no detections must give AP = 0"
    good = Pooled(_synthetic(np.random.default_rng(1), 150, noise=0.15, fp_rate=1.0), 4)
    bad = Pooled(_synthetic(np.random.default_rng(1), 150, noise=0.5, fp_rate=3.0), 4)
    flat = [flatten(compute_metrics(p), names) for p in (good, bad)]
    assert flat[0]["map50"] > flat[1]["map50"], "better detections must score higher"
    samples = bootstrap_samples([good, bad], [compute_metrics(p)["op_idx"] for p in (good, bad)], names, 60, 7)
    ci = interval(samples[0]["map50"], flat[0]["map50"], 0.95)
    assert ci["lo"] <= ci["point"] <= ci["hi"], f"point estimate outside its own bootstrap CI: {ci}"
    delta = interval(samples[0]["map50"] - samples[1]["map50"], flat[0]["map50"] - flat[1]["map50"], 0.95)
    assert delta["lo"] > 0, f"clearly better model should have a positive paired delta CI: {delta}"
    print(f"selftest OK: good mAP50 {flat[0]['map50']:.3f} {ci}, bad {flat[1]['map50']:.3f}, delta {delta}")
    return 0


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate .pt weights on a data.yaml split with bootstrap CIs")
    ap.add_argument("--weights", nargs="+", type=Path, help="one or more .pt files; with several, the first is the reference")
    ap.add_argument("--data", type=Path, help="Ultralytics data.yaml")
    ap.add_argument("--split", default="test", help="train | val | test (default test)")
    ap.add_argument("--tag", help="name used in output files (<stem>_eval_<tag>.json, eval_compare_<tag>.*); default = split. Use e.g. `field` for the field yaml so it does not overwrite the India results")
    ap.add_argument("--labels", nargs="+", help="column names for the comparison table, one per weights file")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="")
    ap.add_argument("--conf", type=float, default=0.001, help="confidence floor for the PR curves (leave at 0.001)")
    ap.add_argument("--iou", type=float, default=0.6, help="NMS IoU (Ultralytics val default)")
    ap.add_argument("--max-det", type=int, default=300)
    ap.add_argument("--boot", type=int, default=1000, help="bootstrap resamples over images; 0 disables")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ci", type=float, default=0.95, help="confidence level")
    ap.add_argument("--out", type=Path, help="JSON path (single weights only). Default: next to the weights")
    ap.add_argument("--no-val", action="store_true", help="skip the model.val() cross-check")
    ap.add_argument("--limit", type=int, default=0, help="only the first N images (smoke test)")
    ap.add_argument("--dry-run", action="store_true", help="resolve yaml + images + labels and stop; no model needed")
    ap.add_argument("--selftest", action="store_true", help="numpy-only check of the metric and bootstrap code")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.data:
        ap.error("--data is required")
    if not args.dry_run and not args.weights:
        ap.error("--weights is required")
    if args.out and args.weights and len(args.weights) > 1:
        ap.error("--out only works with a single --weights file")
    if args.labels and args.weights and len(args.labels) != len(args.weights):
        ap.error("--labels needs one name per --weights file")

    ctx = make_ctx(args.data, args.split, imgsz=args.imgsz, batch=args.batch, device=args.device, conf=args.conf, iou=args.iou, max_det=args.max_det, limit=args.limit)
    with_label = sum(1 for p in ctx.images if label_for(p).is_file())
    print(f"data={ctx.data} split={ctx.split} images={len(ctx.images)} with_label_file={with_label} classes={ctx.names} device={ctx.device}")
    if with_label < len(ctx.images):
        print(f"[note] {len(ctx.images) - with_label} images have no label file and count as background.")
    if args.dry_run:
        return 0

    for w in args.weights:
        if not Path(w).is_file():
            print(f"weights not found: {w}", file=sys.stderr)
            return 2
    payloads, comparison = evaluate_many(args.weights, ctx, boot=args.boot, seed=args.seed, level=args.ci, run_val=not args.no_val, labels=args.labels)
    for p in payloads:
        print_payload(p, ctx.names)
    tag = args.tag or ctx.split
    for w, p in zip(args.weights, payloads):
        write_json(args.out or default_out(w, tag), p)
    if comparison is not None:
        if args.boot > 0:
            table = comparison_table(comparison, ctx.names)
            print("\n" + table)
        else:
            table = "(no bootstrap: rerun without --boot 0 for the comparison table)"
        base = Path(args.weights[0]).resolve().parent
        write_json(base / f"eval_compare_{tag}.json", comparison)
        (base / f"eval_compare_{tag}.md").write_text(table + "\n", encoding="utf-8")
        print(f"wrote {base / f'eval_compare_{tag}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
