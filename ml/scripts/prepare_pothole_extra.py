"""Add public pothole photos to a training mix. Val and test stay the base mix's India val and test.

Why: the shipped detector misses big, close-up and water-filled potholes. In the RDD training data a pothole box covers a
median 0.6% of the image; in the Kent photos it is 7.9%. The detector has hardly seen a pothole that size.

  python ml/scripts/prepare_pothole_extra.py --src kent=data/pothole_kent/raw
  python ml/scripts/prepare_pothole_extra.py --src kent=data/pothole_kent/raw --src rf665=data/pothole_roboflow/raw --class-map 0=3
  python ml/scripts/prepare_pothole_extra.py --src kent=data/pothole_kent/raw --dry-run     # count only, write nothing

--src NAME=DIR   a folder of photos with YOLO .txt labels (any layout: IMG/ + TXT/, images/ + labels/, or all in one folder).
                 Files become pothole_<NAME>_<original name>; train_rdd.py --domain-weight pothole_=2 draws them twice as often.
--class-map      source class id -> RDD class id, "0=3" by default (one pothole class -> D40). A source class that is not
                 mapped stops the run: map it on purpose, never silently.

The base mix (default data/rdd_simsplit_mix) is never changed. Its files are hard-linked into --out
(default data/rdd_simsplit_pothole_mix), so the extra folder costs almost no disk.

Safety checks, reported at the end:
- boxes that fall outside the image (broken labels) are dropped; a photo left with no box is skipped, never kept as clean road
- exact duplicate photos are dropped, and any photo identical to a base val/test image is refused
- a block of consecutive photos per source is held out as <NAME>_holdout (data_<NAME>_holdout.yaml, test split). Nothing in it
  is trained on. It is a check on that dataset's kind of photo, not field evidence: only your own labelled phone photos are.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MIX = ROOT / "data" / "rdd_simsplit_mix"
OUT_MIX = ROOT / "data" / "rdd_simsplit_pothole_mix"
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
LABEL_DIRS = {"txt", "labels", "label"}
INFO_NAME = "pothole_extra_info.json"
D40 = 3
EDGE_TOL = 0.002  # a box may sit this far outside the image (rounding) and is clipped; further out it is a broken label


def _natural(path: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _link_or_copy(src: Path, dest: Path, copy: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    if not copy:
        try:
            os.link(src, dest)
            return
        except OSError:
            pass
    shutil.copy2(src, dest)


def _yaml_text(out: Path, test: str) -> str:
    return (
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"test: {test}\n"
        "nc: 4\n"
        "names: [D00, D10, D20, D40]\n"
    )


def parse_class_map(text: str) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        src, _, dst = part.partition("=")
        try:
            mapping[int(src)] = int(dst)
        except ValueError:
            raise SystemExit(f"--class-map: '{part}' is not SRC=DST (e.g. 0=3)")
        if not 0 <= mapping[int(src)] <= 3:
            raise SystemExit(f"--class-map: destination {dst} is not an RDD class id (0-3 = D00 D10 D20 D40)")
    if not mapping:
        raise SystemExit("--class-map is empty")
    return mapping


def parse_sources(items: list[str]) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for item in items:
        name, _, folder = item.partition("=")
        if not folder or not re.fullmatch(r"[a-z0-9]+", name):
            raise SystemExit(f"--src '{item}': use NAME=DIR with NAME in lower-case letters and digits, e.g. kent=data/pothole_kent/raw")
        path = Path(folder)
        path = path if path.is_absolute() else ROOT / path
        if not path.is_dir():
            raise SystemExit(f"--src {name}: {path} is not a folder")
        if name in {n for n, _ in sources}:
            raise SystemExit(f"--src: name '{name}' used twice")
        sources.append((name, path))
    return sources


def label_index(src: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for p in src.rglob("*.txt"):
        if p.stem.lower() in {"readme", "classes", "labels", "train", "valid", "val", "test"}:
            continue
        index.setdefault(p.stem, []).append(p)
    return index


def find_label(img: Path, index: dict[str, list[Path]]) -> Path | None:
    found = index.get(img.stem, [])
    if len(found) > 1:
        in_label_dir = [p for p in found if p.parent.name.lower() in LABEL_DIRS]
        found = in_label_dir if len(in_label_dir) == 1 else found
    if len(found) > 1:
        raise SystemExit(f"{img.name}: more than one label file with that name: {[str(p) for p in found]}")
    return found[0] if found else None


def read_boxes(label: Path, class_map: dict[int, int], min_side: float, stats: Counter, unmapped: Counter) -> list[tuple[int, float, float, float, float]]:
    boxes: list[tuple[int, float, float, float, float]] = []
    for line in label.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            if len(parts) != 5:
                raise ValueError
            cid = int(float(parts[0]))
            x, y, w, h = (float(v) for v in parts[1:])
        except ValueError:
            stats["bad_lines"] += 1
            continue
        if cid not in class_map:
            unmapped[cid] += 1
            continue
        x1, y1, x2, y2 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
        if w <= 0 or h <= 0 or min(x1, y1) < -EDGE_TOL or max(x2, y2) > 1 + EDGE_TOL:
            stats["boxes_out_of_range"] += 1
            continue
        x1, y1, x2, y2 = (min(1.0, max(0.0, v)) for v in (x1, y1, x2, y2))
        w, h = x2 - x1, y2 - y1
        if w < min_side or h < min_side:
            stats["boxes_too_small"] += 1
            continue
        boxes.append((class_map[cid], (x1 + x2) / 2, (y1 + y2) / 2, w, h))
    return boxes


def pick_holdout(items: list, frac: float, block: int, seed: int) -> set[int]:
    """Whole blocks of consecutive photos, so shots of one place are not split between train and the check."""
    if frac <= 0 or not items:
        return set()
    want = max(1, round(frac * len(items)))
    blocks = [list(range(i, min(i + block, len(items)))) for i in range(0, len(items), block)]
    order = list(range(len(blocks)))
    random.Random(seed).shuffle(order)
    chosen: set[int] = set()
    for b in order:
        if len(chosen) >= want:
            break
        chosen.update(blocks[b])
    return chosen


def base_d40_median(base: Path) -> tuple[int, float]:
    areas: list[float] = []
    for t in (base / "labels" / "train").glob("*.txt"):
        for line in t.read_text(encoding="utf-8", errors="replace").splitlines():
            p = line.split()
            if len(p) == 5 and p[0] == str(D40):
                areas.append(float(p[3]) * float(p[4]))
    return len(areas), (statistics.median(areas) if areas else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Add public pothole photos to a training mix (val/test unchanged)")
    ap.add_argument("--src", action="append", required=True, metavar="NAME=DIR", help="folder of photos + YOLO labels; repeatable")
    ap.add_argument("--class-map", default="0=3", help="source class -> RDD class, e.g. 0=3 (default)")
    ap.add_argument("--base-mix", default=str(BASE_MIX), help="mix whose train/val/test are the starting point")
    ap.add_argument("--out", default=str(OUT_MIX), help="new mix folder (never the base mix)")
    ap.add_argument("--holdout-frac", type=float, default=0.10, help="share of each source kept out of training as NAME_holdout (0 = none)")
    ap.add_argument("--holdout-block", type=int, default=10, help="consecutive photos per held-out block")
    ap.add_argument("--min-side", type=float, default=0.005, help="drop boxes thinner than this fraction of the image")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--copy", action="store_true", help="copy the extra photos instead of hard-linking them")
    ap.add_argument("--rebuild", action="store_true", help="delete --out first (only if it was made by this script)")
    ap.add_argument("--dry-run", action="store_true", help="count and check everything, write nothing")
    args = ap.parse_args()

    base = Path(args.base_mix)
    base = base if base.is_absolute() else ROOT / base
    out = Path(args.out)
    out = out if out.is_absolute() else ROOT / out
    if not (base / "images" / "train").is_dir() or not (base / "images" / "test").is_dir():
        print(f"missing {base}. Build it first (see data/README.md).", file=sys.stderr)
        return 2
    if out.resolve() == base.resolve():
        print("--out must not be the base mix: the base mix stays untouched.", file=sys.stderr)
        return 2
    class_map = parse_class_map(args.class_map)
    sources = parse_sources(args.src)

    if out.exists() and any(out.iterdir()) and not args.dry_run:
        if args.rebuild and (out / INFO_NAME).is_file():
            shutil.rmtree(out)
        else:
            print(f"{out} already exists. Pass --rebuild to replace it (only works on a folder this script made).", file=sys.stderr)
            return 2

    # Photos identical to a base val/test image would leak into training.
    blocked: dict[str, str] = {}
    for split in ("val", "test"):
        for p in sorted((base / "images" / split).glob("*")):
            if p.suffix.lower() in IMAGE_EXT:
                blocked[_sha256(p)] = f"{split}/{p.name}"

    report: list[dict] = []
    plan: list[tuple[str, Path, list, str]] = []  # (folder, image, boxes, out file name)
    for name, src in sources:
        prefix = f"pothole_{name}_"
        stats: Counter = Counter()
        unmapped: Counter = Counter()
        index = label_index(src)
        images = sorted((p for p in src.rglob("*") if p.suffix.lower() in IMAGE_EXT), key=_natural)
        stats["images_found"] = len(images)
        seen: dict[str, str] = {}
        usable: list[tuple[Path, list]] = []
        for img in images:
            label = find_label(img, index)
            if label is None:
                stats["skipped_no_label_file"] += 1
                continue
            boxes = read_boxes(label, class_map, args.min_side, stats, unmapped)
            if not boxes:
                stats["skipped_no_usable_box"] += 1
                continue
            digest = _sha256(img)
            if digest in blocked:
                stats["skipped_same_as_base_val_test"] += 1
                continue
            if digest in seen:
                stats["skipped_exact_duplicate"] += 1
                continue
            seen[digest] = img.name
            usable.append((img, boxes))
        if unmapped:
            raise SystemExit(
                f"--src {name}: label class ids {sorted(unmapped)} are not in --class-map {class_map}. "
                f"Map them (e.g. --class-map 0=3,1=3) or fix the labels; nothing was written."
            )
        held = pick_holdout(usable, args.holdout_frac, args.holdout_block, args.seed)
        areas: list[float] = []
        n_train = n_hold = b_train = b_hold = 0
        for i, (img, boxes) in enumerate(usable):
            folder = f"{name}_holdout" if i in held else "train"
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", img.stem)
            plan.append((folder, img, boxes, f"{prefix}{safe}{img.suffix.lower()}"))
            areas.extend(b[3] * b[4] for b in boxes)
            if i in held:
                n_hold += 1
                b_hold += len(boxes)
            else:
                n_train += 1
                b_train += len(boxes)
        report.append(
            {
                "name": name,
                "folder": str(src),
                "prefix": prefix,
                "class_map": class_map,
                "images_used_for_train": n_train,
                "images_held_out": n_hold,
                "boxes_train": b_train,
                "boxes_holdout": b_hold,
                "median_box_area": round(statistics.median(areas), 4) if areas else 0.0,
                "skipped_or_dropped": dict(stats),
            }
        )

    d40_n, d40_med = base_d40_median(base)
    n_train_extra = sum(r["images_used_for_train"] for r in report)
    base_train = sum(1 for _ in (base / "images" / "train").iterdir())

    print(f"base mix: {base.name}  train {base_train} images, D40 boxes {d40_n} (median box area {d40_med:.4f} of the image)")
    for r in report:
        print(f"\nsource {r['name']}  ({r['folder']})")
        print(f"  train {r['images_used_for_train']} images / {r['boxes_train']} boxes, held out {r['images_held_out']} images / {r['boxes_holdout']} boxes")
        print(f"  median pothole box covers {r['median_box_area']:.4f} of the image (RDD train: {d40_med:.4f})")
        for k, v in sorted(r["skipped_or_dropped"].items()):
            if k != "images_found":
                print(f"  {k}: {v}")
    print(f"\nmix would hold {base_train + n_train_extra} train images ({n_train_extra} extra), val and test unchanged")
    if args.dry_run:
        print("dry run: nothing written.")
        return 0

    for split in ("train", "val", "test"):
        for kind in ("images", "labels"):
            for p in (base / kind / split).glob("*"):
                _link_or_copy(p, out / kind / split / p.name)
    names_used: set[tuple[str, str]] = set()
    for folder, img, boxes, out_name in plan:
        if (folder, out_name) in names_used:
            raise SystemExit(f"two photos would both be written as {folder}/{out_name}")
        names_used.add((folder, out_name))
        _link_or_copy(img, out / "images" / folder / out_name, args.copy)
        lbl = out / "labels" / folder / (Path(out_name).stem + ".txt")
        lbl.parent.mkdir(parents=True, exist_ok=True)
        lbl.write_text("".join(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for c, x, y, w, h in boxes), encoding="utf-8")

    (out / "data.yaml").write_text(_yaml_text(out, "images/test"), encoding="utf-8")
    for r in report:
        if r["images_held_out"]:
            (out / f"data_{r['name']}_holdout.yaml").write_text(_yaml_text(out, f"images/{r['name']}_holdout"), encoding="utf-8")
    if (base / "split_info.json").is_file():  # train_rdd.py reads the split mode from here
        shutil.copy2(base / "split_info.json", out / "split_info.json")
    (out / INFO_NAME).write_text(
        json.dumps(
            {
                "schema": "pothole_extra/1",
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "base_mix": str(base),
                "base_train_images": base_train,
                "base_d40_median_box_area": round(d40_med, 4),
                "extra_train_images": n_train_extra,
                "sources": report,
                "settings": {k: v for k, v in vars(args).items() if k != "src"} | {"src": args.src},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    print(f"  train: {out / 'data.yaml'}")
    for r in report:
        if r["images_held_out"]:
            print(f"  {r['name']} holdout check: {out / ('data_' + r['name'] + '_holdout.yaml')}")
    print("Next (not started): train_rdd.py --data data/rdd_simsplit_pothole_mix/data.yaml ... --domain-weight pothole_=2 --class-balanced --no-promote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
