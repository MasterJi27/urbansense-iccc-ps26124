"""Download official RDD2022 and keep only the India split as Ultralytics YOLO.

Source: Figshare 10.6084/m9.figshare.21431547 (CRDDC'2022, CC BY 4.0).
Classes kept: D00 D10 D20 D40. No invented labels. Zip stays under .data/ (gitignored).

  python scripts/prepare_rdd_india.py
  python scripts/prepare_rdd_india.py --zip D:\\path\\RDD2022_released_through_CRDDC2022.zip

Honest-evaluation options (these never touch the frozen .data/rdd_india):

  # NEW yaml in .data/rdd_india_grouped: neighbouring frames never straddle train/val/test
  python scripts/prepare_rdd_india.py --skip-download --skip-extract --split-by-group

  # same, plus a hand-labelled phone/bus-windshield set as a never-trained-on test split
  python scripts/prepare_rdd_india.py --skip-download --skip-extract --split-by-group \\
      --field-test-dir D:\\field_windshield_set

  # are neighbouring filename ids really neighbouring frames? (run this first)
  python scripts/prepare_rdd_india.py --skip-download --skip-extract --audit-neighbours

  # they are not (ids are shuffled): split look-alike clusters instead, in .data/rdd_india_simsplit
  python scripts/prepare_rdd_india.py --skip-download --skip-extract --split-by-similarity
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / ".data"
ZIP_PATH = DATA_ROOT / "RDD2022_released_through_CRDDC2022.zip"
EXTRACT = DATA_ROOT / "rdd2022_raw"
LEGACY_OUT = DATA_ROOT / "rdd_india"  # frozen: the split every published metric so far was measured on
GROUPED_OUT = DATA_ROOT / "rdd_india_grouped"
SIMILAR_OUT = DATA_ROOT / "rdd_india_simsplit"
FIGSHARE = "https://ndownloader.figshare.com/files/38030910"
KEEP = ("D00", "D10", "D20", "D40")
NAME_TO_ID = {name: i for i, name in enumerate(KEEP)}
D10_ID = str(NAME_TO_ID["D10"])
# File duplication of D10 images is OFF by default now: duplicated rows overweight a handful of
# images and hide that D10 is rare. Use `train_rdd.py --class-balanced` (repeat-factor sampler)
# instead. `--d10-repeat 10` reproduces the old build.
D10_TRAIN_REPEAT = 1
SPLIT_SEED = 42
SIM_THRESH = 0.95
MAX_CLUSTER_FRAC = 0.02
GROUP_SIZE = 30
EMBARGO = 2
IMG_EXT = {".jpg", ".jpeg", ".png"}
_ID_RE = re.compile(r"^(.*?)(\d+)$")


def _is_india_member(name: str) -> bool:
    n = name.replace("\\", "/")
    return "/India/" in n or n.startswith("India/") or "/India_" in n


def download_zip(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1_000_000_000:
        print(f"using existing {dest} ({dest.stat().st_size} bytes)")
        return
    print(f"downloading official RDD2022 (~13 GB) → {dest}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(FIGSHARE, tmp)
    tmp.replace(dest)


def extract_india(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    nested = dest / "India.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        inner = next((n for n in names if n.replace("\\", "/").endswith("India.zip")), None)
        members = [m for m in names if _is_india_member(m) and not m.lower().endswith(".zip")]
        if inner:
            print(f"extracting nested {inner}")
            if not nested.is_file() or nested.stat().st_size < 1_000_000:
                with zf.open(inner) as src, nested.open("wb") as out:
                    shutil.copyfileobj(src, out)
            with zipfile.ZipFile(nested) as india:
                india.extractall(dest / "India")
            return
        if not members:
            raise SystemExit("Zip has no India/ paths. Check the Figshare archive.")
        print(f"extracting {len(members)} India members")
        for name in members:
            zf.extract(name, dest)


def _iter_xml(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.xml") if "India" in str(p).replace("\\", "/"))


def _image_for_xml(xml_path: Path) -> Path | None:
    stem = xml_path.stem
    for folder in (xml_path.parent, xml_path.parent.parent, xml_path.parent.parent / "images", xml_path.parent.parent / "JPEGImages"):
        for ext in (".jpg", ".jpeg", ".png", ".JPG"):
            cand = folder / f"{stem}{ext}"
            if cand.is_file():
                return cand
    hits = list(xml_path.parents[2].rglob(f"{stem}.jpg")) if len(xml_path.parents) >= 2 else []
    return hits[0] if hits else None


def voc_to_yolo(xml_path: Path) -> list[str]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    if size is None:
        return []
    w = float(size.findtext("width") or 0)
    h = float(size.findtext("height") or 0)
    if w <= 0 or h <= 0:
        return []
    lines: list[str] = []
    for obj in root.findall("object"):
        name = (obj.findtext("name") or "").strip()
        if name not in NAME_TO_ID:
            continue
        box = obj.find("bndbox")
        if box is None:
            continue
        xmin = float(box.findtext("xmin") or 0)
        ymin = float(box.findtext("ymin") or 0)
        xmax = float(box.findtext("xmax") or 0)
        ymax = float(box.findtext("ymax") or 0)
        xc = ((xmin + xmax) / 2.0) / w
        yc = ((ymin + ymax) / 2.0) / h
        bw = max(0.0, (xmax - xmin) / w)
        bh = max(0.0, (ymax - ymin) / h)
        if bw <= 0 or bh <= 0:
            continue
        lines.append(f"{NAME_TO_ID[name]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return lines


def _has_d10(labels: list[str]) -> bool:
    return any(line.startswith(f"{D10_ID} ") for line in labels)


def _place(src: Path, dest: Path, copy: bool) -> None:
    """Hard-link (same volume, no extra disk) or copy src to dest; never overwrites."""
    if dest.exists():
        return
    if not copy:
        try:
            os.link(src, dest)
            return
        except OSError:
            pass
    shutil.copy2(src, dest)


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_split(pairs: list[tuple[Path, Path]], split: str, out: Path, *, d10_repeat: int = 1, copy: bool = False) -> tuple[int, Counter, int]:
    """Write one split. Returns (files written, class-instance counts, images skipped for having no kept label)."""
    img_dir = out / "images" / split
    lbl_dir = out / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    n = skipped = 0
    inst: Counter = Counter()
    for img, xml in pairs:
        labels = voc_to_yolo(xml)
        if not labels:
            skipped += 1
            continue
        copies = max(1, d10_repeat) if split == "train" and _has_d10(labels) else 1
        text = "\n".join(labels) + "\n"
        for i in range(copies):
            stem = img.stem if i == 0 else f"{img.stem}_d10x{i}"
            _place(img, img_dir / f"{stem}{img.suffix}", copy)
            (lbl_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
            n += 1
            inst.update(KEEP[int(line.split()[0])] for line in labels)
    return n, inst, skipped


def _reset_dirs(out: Path) -> None:
    for name in ("images", "labels"):
        folder = out / name
        if folder.exists():
            shutil.rmtree(folder)


# --------------------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------------------
def parse_id(stem: str) -> tuple[str, int] | None:
    """'India_000123' -> ('India_', 123). None when the name carries no trailing number."""
    m = _ID_RE.match(stem)
    return (m.group(1), int(m.group(2))) if m else None


def split_random(pairs: list[tuple[Path, Path]], seed: int) -> dict[str, list[tuple[Path, Path]]]:
    """The original per-image shuffle (kept so the frozen split can be rebuilt bit-for-bit)."""
    pairs = list(pairs)
    random.Random(seed).shuffle(pairs)
    n = len(pairs)
    train_end = max(1, int(n * 0.8))
    val_end = max(train_end + 1, int(n * 0.9))
    return {"train": pairs[:train_end], "val": pairs[train_end:val_end], "test": pairs[val_end:]}


def split_grouped(pairs: list[tuple[Path, Path]], seed: int, group_size: int, embargo: int) -> tuple[dict[str, list[tuple[Path, Path]]], dict]:
    """Split whole blocks of neighbouring filename ids, then enforce a gap around val/test.

    1. Images are bucketed by (name prefix, id // group_size). Whole buckets go to one split, so
       adjacent frames only meet at bucket edges. Names without a trailing number are their own bucket.
    2. Buckets are shuffled (seeded) and filled 80/10/10 by image count.
    3. Embargo: images within `embargo` ids of a test image are dropped from val, and images within
       `embargo` ids of a val/test image are dropped from train, so a bucket edge cannot leak a
       near-duplicate frame across splits.
    """
    groups: dict[tuple, list[tuple[Path, Path]]] = {}
    unnumbered = 0
    for pair in pairs:
        pid = parse_id(pair[0].stem)
        if pid is None:
            key: tuple = ("__single__", pair[0].stem)
            unnumbered += 1
        else:
            key = (pid[0], pid[1] // max(1, group_size))
        groups.setdefault(key, []).append(pair)
    keys = sorted(groups, key=lambda k: (str(k[0]), str(k[1])))
    random.Random(seed).shuffle(keys)
    n = len(pairs)
    train_target, val_target = int(n * 0.8), int(n * 0.9)
    out: dict[str, list[tuple[Path, Path]]] = {"train": [], "val": [], "test": []}
    seen = 0
    for key in keys:
        split = "train" if seen < train_target else "val" if seen < val_target else "test"
        out[split] += groups[key]
        seen += len(groups[key])

    def ids(split_pairs: list[tuple[Path, Path]]) -> set[tuple[str, int]]:
        return {pid for pid in (parse_id(p[0].stem) for p in split_pairs) if pid is not None}

    def near(pid: tuple[str, int] | None, blocked: set[tuple[str, int]]) -> bool:
        if pid is None or embargo <= 0:
            return False
        return any((pid[0], pid[1] + d) in blocked for d in range(-embargo, embargo + 1) if d)

    test_ids = ids(out["test"])
    val_kept = [p for p in out["val"] if not near(parse_id(p[0].stem), test_ids)]
    dropped_val = len(out["val"]) - len(val_kept)
    out["val"] = val_kept
    eval_ids = test_ids | ids(out["val"])
    train_kept = [p for p in out["train"] if not near(parse_id(p[0].stem), eval_ids)]
    dropped_train = len(out["train"]) - len(train_kept)
    out["train"] = train_kept
    info = {
        "n_groups": len(groups),
        "median_group_images": int(sorted(len(g) for g in groups.values())[len(groups) // 2]),
        "unnumbered_images": unnumbered,
        "embargo_dropped_val": dropped_val,
        "embargo_dropped_train": dropped_train,
    }
    return out, info


def _thumb(path: Path):
    """Zero-mean, unit-norm 32x32 grey thumbnail. Cosine >= ~0.95 means the same spot of the same drive."""
    from PIL import Image  # shipped with ultralytics
    import numpy as np

    with Image.open(path) as im:
        a = np.asarray(im.convert("L").resize((32, 32), Image.BILINEAR), dtype=np.float32).ravel()
    a -= a.mean()
    return a / (np.linalg.norm(a) + 1e-6)


def split_similar(pairs: list[tuple[Path, Path]], seed: int, thresh: float, max_cluster_frac: float) -> tuple[dict[str, list[tuple[Path, Path]]], dict]:
    """Split whole clusters of look-alike images, so the same spot of a drive never straddles splits.

    RDD2022 India filename ids are shuffled (--audit-neighbours), so blocks of ids do not group
    frames of one drive. Instead: link every two labelled images whose thumbnail cosine is
    >= thresh, take connected components, send components bigger than max_cluster_frac of the
    images to train, shuffle the rest (seeded) and fill test, then val, to 10% each by image
    count. By construction no val/test image has a train image (or a test image a val image)
    at or above thresh.
    """
    import numpy as np

    pairs = [p for p in pairs if voc_to_yolo(p[1])]  # only images that get written count toward 80/10/10
    feats = np.stack([_thumb(img) for img, _ in pairs])
    sim = feats @ feats.T
    np.fill_diagonal(sim, -1.0)
    parent = list(range(len(pairs)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in zip(*np.nonzero(np.triu(sim >= thresh))):
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    comps: dict[int, list[int]] = {}
    for i in range(len(pairs)):
        comps.setdefault(find(i), []).append(i)
    big = max(2, int(len(pairs) * max_cluster_frac))
    forced = [c for c in comps.values() if len(c) > big]
    rest = sorted((c for c in comps.values() if len(c) <= big), key=lambda c: pairs[c[0]][0].name)
    random.Random(seed).shuffle(rest)
    target = int(len(pairs) * 0.1)
    idx: dict[str, list[int]] = {"train": [i for c in forced for i in c], "val": [], "test": []}
    for comp in rest:
        split = "test" if len(idx["test"]) < target else "val" if len(idx["val"]) < target else "train"
        idx[split] += comp

    def cross(a: str, b: str) -> float:
        return round(float(sim[np.ix_(idx[a], idx[b])].max()), 4) if idx[a] and idx[b] else 0.0

    sizes = sorted((len(c) for c in comps.values()), reverse=True)
    info = {
        "sim_thresh": thresh,
        "n_clusters": len(comps),
        "largest_clusters": sizes[:5],
        "images_in_multi_clusters": sum(s for s in sizes if s > 1),
        "clusters_forced_to_train": len(forced),
        "max_cross_split_cosine": {"val_train": cross("val", "train"), "test_train": cross("test", "train"), "test_val": cross("test", "val")},
    }
    return {k: [pairs[i] for i in sorted(v)] for k, v in idx.items()}, info


# --------------------------------------------------------------------------------------
# Audit: are neighbouring ids neighbouring frames?
# --------------------------------------------------------------------------------------
def _dhash(path: Path):
    from PIL import Image  # shipped with ultralytics
    import numpy as np

    with Image.open(path) as im:
        a = np.asarray(im.convert("L").resize((9, 8)), dtype=float)
    return (a[:, 1:] > a[:, :-1]).ravel()


def audit_neighbours(pairs: list[tuple[Path, Path]], samples: int = 300) -> None:
    import numpy as np

    by_id: dict[tuple[str, int], Path] = {}
    for img, _ in pairs:
        pid = parse_id(img.stem)
        if pid is not None:
            by_id[pid] = img
    consecutive = [(by_id[k], by_id[(k[0], k[1] + 1)]) for k in sorted(by_id) if (k[0], k[1] + 1) in by_id]
    if len(consecutive) < 20:
        print("Too few consecutive-id pairs to audit; filenames carry no usable sequence ids. Use the random split.")
        return
    rng = random.Random(0)
    near_pairs = rng.sample(consecutive, min(samples, len(consecutive)))
    allimgs = list(by_id.values())
    far_pairs = [tuple(rng.sample(allimgs, 2)) for _ in range(len(near_pairs))]

    def dist(ps) -> list[int]:
        return [int((_dhash(a) != _dhash(b)).sum()) for a, b in ps]

    near_d, far_d = dist(near_pairs), dist(far_pairs)
    mn, mf = float(np.median(near_d)), float(np.median(far_d))
    print(f"dHash Hamming distance (0 = identical, 64 = unrelated): id-neighbours median {mn:.1f}, random pairs median {mf:.1f}")
    print(f"  id-neighbours within 10 bits: {np.mean([d <= 10 for d in near_d]):.0%}; random pairs within 10 bits: {np.mean([d <= 10 for d in far_d]):.0%}")
    if mn <= 0.6 * mf:
        print("=> neighbouring ids look like neighbouring frames. --split-by-group is meaningful; try --group-size 30-100.")
    else:
        print("=> neighbouring ids do NOT look more alike than random pairs. Grouping by id will not remove leakage; find the true sequence key first.")


# --------------------------------------------------------------------------------------
# Field set
# --------------------------------------------------------------------------------------
def collect_field(field_dir: Path, *, missing_as_background: bool) -> list[tuple[Path, Path | None]]:
    """Hand-labelled windshield images in YOLO format. Layout: <dir>/images + <dir>/labels, or flat."""
    img_root = field_dir / "images" if (field_dir / "images").is_dir() else field_dir
    lbl_root = field_dir / "labels" if (field_dir / "labels").is_dir() else field_dir
    imgs = sorted(p for p in img_root.rglob("*") if p.suffix.lower() in IMG_EXT)
    if not imgs:
        raise SystemExit(f"--field-test-dir: no images under {img_root}")
    out: list[tuple[Path, Path | None]] = []
    errors: list[str] = []
    missing = 0
    for img in imgs:
        lbl = (lbl_root / img.relative_to(img_root)).with_suffix(".txt")
        if not lbl.is_file():
            missing += 1
            out.append((img, None))
            continue
        for ln, line in enumerate(lbl.read_text(encoding="utf-8").splitlines(), 1):
            parts = line.split()
            if not parts:
                continue
            try:
                cls, *box = parts
                ok = len(parts) == 5 and cls.isdigit() and 0 <= int(cls) < len(KEEP) and all(-1e-3 <= float(v) <= 1 + 1e-3 for v in box) and float(box[2]) > 0 and float(box[3]) > 0
            except ValueError:
                ok = False
            if not ok:
                errors.append(f"{lbl}:{ln}: {line!r}")
        out.append((img, lbl))
    if errors:
        raise SystemExit("--field-test-dir: bad label lines (need `class xc yc w h`, class 0-3 = D00 D10 D20 D40, normalised):\n  " + "\n  ".join(errors[:10]) + (f"\n  ... {len(errors)} total" if len(errors) > 10 else ""))
    if missing and not missing_as_background:
        raise SystemExit(f"--field-test-dir: {missing}/{len(imgs)} images have no label file. A missing file is ambiguous (unlabelled or clean road?). Write an EMPTY .txt for clean-road images, or pass --field-missing-as-background.")
    return out


def write_field(items: list[tuple[Path, Path | None]], out: Path, copy: bool, india_files: list[Path]) -> tuple[int, Counter, int]:
    """Register the field set as images/field + labels/field; refuse if any image is also in the India data."""
    field_sizes = {img.stat().st_size for img, _ in items}
    candidates = [p for p in india_files if p.stat().st_size in field_sizes]  # only hash files whose size matches
    if candidates:
        cand_sizes = {p.stat().st_size for p in candidates}
        india_hashes = {_sha1(p) for p in candidates}
        clash = [img.name for img, _ in items if img.stat().st_size in cand_sizes and _sha1(img) in india_hashes]
        if clash:
            raise SystemExit(f"--field-test-dir: {len(clash)} field images are byte-identical to RDD India images (e.g. {clash[:3]}). A field test set must be disjoint from training data.")
    img_dir, lbl_dir = out / "images" / "field", out / "labels" / "field"
    for folder in (img_dir, lbl_dir):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    inst: Counter = Counter()
    background = 0
    used: set[str] = set()
    for img, lbl in items:
        name = img.stem
        while name in used:
            name += "_"
        used.add(name)
        _place(img, img_dir / f"{name}{img.suffix.lower()}", copy)
        text = lbl.read_text(encoding="utf-8") if lbl is not None else ""
        (lbl_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        rows = [ln.split()[0] for ln in text.splitlines() if ln.strip()]
        inst.update(KEEP[int(c)] for c in rows)
        background += 0 if rows else 1
    return len(items), inst, background


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------
def _yaml_text(out: Path, test: str) -> str:
    return "\n".join(
        [
            f"path: {out.resolve().as_posix()}",
            "train: images/train",
            "val: images/val",
            f"test: {test}",
            "nc: 4",
            "names: [D00, D10, D20, D40]",
            "",
        ]
    )


def build_pairs(raw: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for xml in _iter_xml(raw):
        img = _image_for_xml(xml)
        if img is None:
            continue
        pairs.append((img, xml))
    if len(pairs) < 50:
        raise SystemExit(f"Only {len(pairs)} India image/xml pairs. Conversion aborted.")
    return pairs


def convert(raw: Path, out: Path, args: argparse.Namespace) -> Path:
    pairs = build_pairs(raw)
    if args.split_by_group:
        splits, ginfo = split_grouped(pairs, args.seed, args.group_size, args.embargo)
        mode = "group"
    elif args.split_by_similarity:
        splits, ginfo = split_similar(pairs, args.seed, args.sim_thresh, args.max_cluster_frac)
        mode = "similarity"
    else:
        splits, ginfo = split_random(pairs, args.seed), {}
        mode = "random"
    field_items = collect_field(args.field_test_dir, missing_as_background=args.field_missing_as_background) if args.field_test_dir else None
    _reset_dirs(out)
    counts: dict[str, int] = {}
    classes: dict[str, dict[str, int]] = {}
    skipped = 0
    for split in ("train", "val", "test"):
        n, inst, sk = write_split(splits[split], split, out, d10_repeat=args.d10_repeat if split == "train" else 1, copy=args.copy)
        counts[split], classes[split], skipped = n, dict(inst), skipped + sk
    info: dict = {
        "source": "RDD2022 India (CRDDC)",
        "mode": mode,
        "seed": args.seed,
        "group_size": args.group_size if mode == "group" else None,
        "embargo": args.embargo if mode == "group" else None,
        "d10_train_repeat": args.d10_repeat,
        "counts": counts,
        "class_instances": classes,
        "images_without_kept_labels_skipped": skipped,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **ginfo,
    }
    (out / "data.yaml").write_text(_yaml_text(out, "images/test"), encoding="utf-8")
    msg = f"India YOLO ({mode}) train={counts['train']} val={counts['val']} test={counts['test']} d10_repeat={args.d10_repeat} yaml={out / 'data.yaml'}"
    if field_items is not None:
        india_files = [p for split in ("train", "val", "test") for p in (out / "images" / split).iterdir()]
        n, inst, background = write_field(field_items, out, args.copy, india_files)
        (out / "data_field.yaml").write_text(_yaml_text(out, "images/field"), encoding="utf-8")
        counts["field"], classes["field"], info["field_background_images"] = n, dict(inst), background
        info["field_test_dir"] = str(args.field_test_dir.resolve())
        msg += f"\nfield test set: {n} images ({background} clean-road), instances {dict(inst)}; yaml={out / 'data_field.yaml'} (test: images/field, never in train/val)"
    (out / "split_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(msg)
    for split in ("train", "val", "test"):
        print(f"  {split:5s} class instances {classes[split]}")
    if mode == "similarity":
        print(f"  clusters={ginfo['n_clusters']} largest={ginfo['largest_clusters']} forced_to_train={ginfo['clusters_forced_to_train']} max cross-split cosine={ginfo['max_cross_split_cosine']} (thresh {ginfo['sim_thresh']})")
    elif ginfo:
        print(f"  groups={ginfo['n_groups']} median_group_images={ginfo['median_group_images']} unnumbered={ginfo['unnumbered_images']} embargo_dropped val={ginfo['embargo_dropped_val']} train={ginfo['embargo_dropped_train']}")
    print(f"  {skipped} images had no D00/D10/D20/D40 box and were left out (so val/test contain no empty-road images).")
    return out / "data.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Official RDD2022 India → YOLO yaml")
    parser.add_argument("--zip", type=Path, default=ZIP_PATH)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--out-dir", type=Path, help=f"default {LEGACY_OUT.name}; {GROUPED_OUT.name} with --split-by-group")
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument("--split-by-group", action="store_true", help="keep neighbouring filename ids in one split (writes a NEW yaml, never the frozen rdd_india)")
    parser.add_argument("--group-size", type=int, default=GROUP_SIZE, help="consecutive ids per block for --split-by-group")
    parser.add_argument("--embargo", type=int, default=EMBARGO, help="drop images within N ids of a val/test image from val/train")
    parser.add_argument("--split-by-similarity", action="store_true", help="keep look-alike images (same spot of one drive) in one split; India ids are shuffled, so use this instead of --split-by-group")
    parser.add_argument("--sim-thresh", type=float, default=SIM_THRESH, help="thumbnail cosine at or above which two images count as the same spot")
    parser.add_argument("--max-cluster-frac", type=float, default=MAX_CLUSTER_FRAC, help="look-alike clusters bigger than this fraction of the images go to train")
    parser.add_argument("--field-test-dir", type=Path, help="hand-labelled YOLO windshield set (images/ + labels/) registered as test split `field` in data_field.yaml")
    parser.add_argument("--field-missing-as-background", action="store_true", help="treat field images without a label file as clean road")
    parser.add_argument("--d10-repeat", type=int, default=D10_TRAIN_REPEAT, help="duplicate D10 train images N times (1 = off, old builds used 10; prefer train_rdd.py --class-balanced)")
    parser.add_argument("--copy", action="store_true", help="copy image files instead of hard-linking them")
    parser.add_argument("--audit-neighbours", action="store_true", help="check whether neighbouring ids are neighbouring frames, then exit")
    args = parser.parse_args()
    if args.split_by_group and args.split_by_similarity:
        print("pick one of --split-by-group / --split-by-similarity", file=sys.stderr)
        return 2
    out = (args.out_dir or (GROUPED_OUT if args.split_by_group else SIMILAR_OUT if args.split_by_similarity else LEGACY_OUT)).resolve()
    if out == LEGACY_OUT.resolve() and (args.split_by_group or args.split_by_similarity or args.field_test_dir):
        print(f"refusing to write {out}: it is the frozen split behind the published metrics. Pass a different --out-dir.", file=sys.stderr)
        return 2
    if not args.skip_download:
        try:
            download_zip(args.zip)
        except Exception as exc:
            print(f"download failed: {exc}", file=sys.stderr)
            if not args.zip.is_file():
                return 2
    already = any(EXTRACT.rglob("*.xml"))
    if args.skip_extract and already:
        print(f"using extracted India under {EXTRACT}")
    else:
        if not args.zip.is_file():
            print(f"missing zip {args.zip}", file=sys.stderr)
            return 2
        extract_india(args.zip, EXTRACT)
    if args.audit_neighbours:
        audit_neighbours(build_pairs(EXTRACT))
        return 0
    convert(EXTRACT, out, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
