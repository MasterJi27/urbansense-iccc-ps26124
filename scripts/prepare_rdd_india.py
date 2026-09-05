"""Download official RDD2022 and keep only the India split as Ultralytics YOLO.

Source: Figshare 10.6084/m9.figshare.21431547 (CRDDC'2022, CC BY 4.0).
Classes kept: D00 D10 D20 D40. No invented labels. Zip stays under .data/ (gitignored).

  python scripts/prepare_rdd_india.py
  python scripts/prepare_rdd_india.py --zip D:\\path\\RDD2022_released_through_CRDDC2022.zip
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / ".data"
ZIP_PATH = DATA_ROOT / "RDD2022_released_through_CRDDC2022.zip"
EXTRACT = DATA_ROOT / "rdd2022_raw"
YOLO = DATA_ROOT / "rdd_india"
FIGSHARE = "https://ndownloader.figshare.com/files/38030910"
KEEP = ("D00", "D10", "D20", "D40")
NAME_TO_ID = {name: i for i, name in enumerate(KEEP)}
D10_ID = str(NAME_TO_ID["D10"])
D10_TRAIN_REPEAT = 10
SPLIT_SEED = 42


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


def write_split(pairs: list[tuple[Path, Path]], split: str, *, d10_repeat: int = 1) -> int:
    img_dir = YOLO / "images" / split
    lbl_dir = YOLO / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for img, xml in pairs:
        labels = voc_to_yolo(xml)
        if not labels:
            continue
        copies = d10_repeat if split == "train" and _has_d10(labels) else 1
        text = "\n".join(labels) + "\n"
        for i in range(copies):
            stem = img.stem if i == 0 else f"{img.stem}_d10x{i}"
            dest = img_dir / f"{stem}{img.suffix}"
            if not dest.exists():
                shutil.copy2(img, dest)
            (lbl_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
            n += 1
    return n


def _reset_yolo_dirs() -> None:
    for name in ("images", "labels"):
        folder = YOLO / name
        if folder.exists():
            shutil.rmtree(folder)


def convert(raw: Path) -> Path:
    xmls = _iter_xml(raw)
    pairs: list[tuple[Path, Path]] = []
    for xml in xmls:
        img = _image_for_xml(xml)
        if img is None:
            continue
        pairs.append((img, xml))
    if len(pairs) < 50:
        raise SystemExit(f"Only {len(pairs)} India image/xml pairs. Conversion aborted.")
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(pairs)
    n = len(pairs)
    train_end = max(1, int(n * 0.8))
    val_end = max(train_end + 1, int(n * 0.9))
    _reset_yolo_dirs()
    train_n = write_split(pairs[:train_end], "train", d10_repeat=D10_TRAIN_REPEAT)
    val_n = write_split(pairs[train_end:val_end], "val")
    test_n = write_split(pairs[val_end:], "test")
    yaml = YOLO / "data.yaml"
    yaml.write_text(
        "\n".join(
            [
                f"path: {YOLO.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "nc: 4",
                "names: [D00, D10, D20, D40]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"India YOLO train={train_n} val={val_n} test={test_n} d10_repeat={D10_TRAIN_REPEAT} yaml={yaml}")
    return yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Official RDD2022 India → YOLO yaml")
    parser.add_argument("--zip", type=Path, default=ZIP_PATH)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    args = parser.parse_args()
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
    convert(EXTRACT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
