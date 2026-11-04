"""Build an isolated pothole-optimisation dataset from the existing pothole mix.

Why: pothole_ft_v1 early-stopped on the India val split, which the base checkpoint had already
memorised, so `best.pt` was epoch 2 of 30. This builder keeps the same images but adds a
pothole-focused validation split carved out of the Kent *training* photos, in whole blocks with an
embargo, so early stopping watches D40 instead of memorised India frames.

The 70-photo Kent holdout (Pothole-079..148) is copied unchanged and is never used for selection.

Nothing in data/ is modified: every file is hard-linked (same bytes, no extra disk) into a new
folder. Run with --rebuild to replace a folder this script made.

  python ml/scripts/prepare_pothole_opt_v2.py
  python ml/scripts/prepare_pothole_opt_v2.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "rdd_simsplit_pothole_mix"
OUT = ROOT / "data" / "rdd_pothole_opt_v2"
INFO = "pothole_opt_info.json"
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

# Whole 20-photo blocks from the long Kent train runs, 10-photo embargo on both sides.
# The existing holdout is [79-88, 184-195, 301-310, 341-350, 491-500, 541-550, 621-630].
VAL_BLOCKS = [(260, 279), (400, 419), (580, 599), (670, 689)]
EMBARGO_BLOCKS = [
    (250, 259), (280, 289),
    (390, 399), (420, 429),
    (570, 579), (600, 609),
    (660, 669), (690, 699),
]


def natural(path: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def kent_id(path: Path) -> int | None:
    m = re.search(r"Pothole-(\d+)", path.stem)
    return int(m.group(1)) if m else None


def link(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def in_ranges(value: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= value <= hi for lo, hi in ranges)


def label_for(images_dir: Path, labels_dir: Path, img: Path) -> Path:
    lbl = labels_dir / f"{img.stem}.txt"
    if not lbl.is_file():
        raise SystemExit(f"missing label for {images_dir / img.name}: {lbl}")
    return lbl


def count_classes(labels_dir: Path) -> dict[str, int]:
    counts: Counter = Counter()
    for txt in labels_dir.glob("*.txt"):
        for line in txt.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 5:
                counts[str(int(float(parts[0])))] += 1
    names = {0: "D00", 1: "D10", 2: "D20", 3: "D40"}
    return {names[int(k)]: v for k, v in sorted(counts.items(), key=lambda kv: int(kv[0]))}


def yaml_text(out: Path, val: str, test: str) -> str:
    return (
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        f"val: {val}\n"
        f"test: {test}\n"
        "nc: 4\n"
        "names: [D00, D10, D20, D40]\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Kent-val dataset for pothole optimisation (hard links, source untouched)")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--rebuild", action="store_true", help="replace --out, only if this script wrote it")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.src) if Path(args.src).is_absolute() else ROOT / args.src
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    if not (src / "images" / "train").is_dir():
        print(f"missing {src}. Build data/rdd_simsplit_pothole_mix first.", file=sys.stderr)
        return 2
    if out.resolve() == src.resolve():
        print("--out must differ from --src", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()) and not args.dry_run:
        if args.rebuild and (out / INFO).is_file():
            shutil.rmtree(out)
        else:
            print(f"{out} exists; pass --rebuild to replace a folder this script made.", file=sys.stderr)
            return 2

    plan: dict[str, list[Path]] = {k: [] for k in ("train", "val", "test", "kent_val", "kent_holdout")}
    kent_counts: Counter = Counter()

    for img in sorted((src / "images" / "train").iterdir(), key=natural):
        if img.suffix.lower() not in IMAGE_EXT:
            continue
        kid = kent_id(img) if img.name.startswith("pothole_kent_") else None
        if kid is None:
            plan["train"].append(img)
            continue
        if in_ranges(kid, VAL_BLOCKS):
            plan["kent_val"].append(img)
            kent_counts["kent_val"] += 1
        elif in_ranges(kid, EMBARGO_BLOCKS):
            kent_counts["embargo_dropped"] += 1
        else:
            plan["train"].append(img)
            kent_counts["kent_train"] += 1

    for split in ("val", "test", "kent_holdout"):
        folder = src / "images" / ("kent_holdout" if split == "kent_holdout" else split)
        for img in sorted(folder.iterdir(), key=natural):
            if img.suffix.lower() in IMAGE_EXT:
                plan[split].append(img)

    # Guardrails: the 70-photo holdout stays intact, and val/embargo never touch it.
    hold_ids = {kent_id(p) for p in plan["kent_holdout"]}
    val_ids = {kent_id(p) for p in plan["kent_val"]}
    embargo_ids = {i for i in (kent_id(p) for p in plan["train"]) if i and in_ranges(i, EMBARGO_BLOCKS)}
    if len(hold_ids) != 70:
        print(f"holdout changed: expected 70 photos, got {len(hold_ids)}", file=sys.stderr)
        return 2
    if (val_ids | embargo_ids) & hold_ids:
        print(f"val/embargo overlaps the holdout: {sorted((val_ids | embargo_ids) & hold_ids)}", file=sys.stderr)
        return 2
    seen: set[str] = set()
    for split, files in plan.items():
        for p in files:
            key = p.name.lower()
            if key in seen:
                print(f"{p.name} appears in more than one split", file=sys.stderr)
                return 2
            seen.add(key)

    print(f"source {src}")
    for split, files in plan.items():
        print(f"  {split:12s} {len(files):6d} images")
    print(f"  Kent train {kent_counts['kent_train']}, val {kent_counts['kent_val']}, embargo dropped {kent_counts['embargo_dropped']}, holdout {len(plan['kent_holdout'])}")
    if args.dry_run:
        print("dry run: nothing written.")
        return 0

    src_split = {"train": "train", "kent_val": "train", "val": "val", "test": "test", "kent_holdout": "kent_holdout"}
    for split, files in plan.items():
        origin = src_split[split]
        for img in files:
            link(img, out / "images" / split / img.name)
            link(label_for(src / "images" / origin, src / "labels" / origin, img),
                 out / "labels" / split / f"{img.stem}.txt")

    (out / "data.yaml").write_text(yaml_text(out, "images/kent_val", "images/test"), encoding="utf-8")
    (out / "data_india_val.yaml").write_text(yaml_text(out, "images/val", "images/val"), encoding="utf-8")
    (out / "data_kent_holdout.yaml").write_text(yaml_text(out, "images/val", "images/kent_holdout"), encoding="utf-8")

    counts = {split: len(files) for split, files in plan.items()}
    classes = {split: count_classes(out / "labels" / split) for split in plan}
    base_info: dict = {}
    try:
        base_info = json.loads((src / "split_info.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    (out / "split_info.json").write_text(
        json.dumps(
            {
                **base_info,
                "source": base_info.get("source", "RDD2022 India + country extras + University of Kent potholes"),
                "mode": (base_info.get("mode") or "similarity") + "+kent-block-val",
                "counts": counts,
                "class_instances": classes,
                "kent_val_blocks": VAL_BLOCKS,
                "kent_embargo_blocks": EMBARGO_BLOCKS,
                "kent_holdout_ids": sorted(hold_ids),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "note": "val is Kent D40 only for checkpoint selection; India val/test must be scored separately",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out / INFO).write_text(
        json.dumps(
            {
                "schema": "pothole_opt/1",
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": str(src),
                "counts": counts,
                "class_instances": classes,
                "kent_val_blocks": VAL_BLOCKS,
                "kent_embargo_blocks": EMBARGO_BLOCKS,
                "kent_holdout_ids": sorted(hold_ids),
                "selection": "best.pt is chosen on kent_val (D40 only); kent_holdout is never used for selection",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    for split in ("train", "kent_val", "val", "test", "kent_holdout"):
        print(f"  {split:12s} {classes[split]}")
    print("  data.yaml -> val=kent_val, test=India test")
    print("  data_india_val.yaml, data_kent_holdout.yaml for final reporting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
