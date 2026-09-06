"""Mix Hugging Face RDD extras into India train. Val/test stay frozen.

Source: TamAko783/Unified_Road_Defect_Dataset (YOLO, 4-class CRDDC).
Keep ground-level RDD-2022 only: Japan, Czech, United_States, China_MotorBike.
Skip India (our split already covers it — no test leak), Norway, drones/UAV.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".data"
INDIA = DATA / "rdd_india"
HF_DIR = DATA / "hf_unified"
MIX = DATA / "rdd_hf_mix"
REPO = "TamAko783/Unified_Road_Defect_Dataset"
TARS = ("data/train_a.tar.gz", "data/train_b.tar.gz")
KEEP_PREFIX = (
    "rdd_Japan_",
    "rdd_Czech_",
    "rdd_United_States_",
    "rdd_China_MotorBike_",
)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}


def _keep(name: str) -> bool:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return any(base.startswith(prefix) for prefix in KEEP_PREFIX)


def _link_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def download_tars() -> list[Path]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise SystemExit("pip install huggingface_hub in the training env")
    HF_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename in TARS:
        print(f"HF download {REPO} {filename}", flush=True)
        local = hf_hub_download(
            repo_id=REPO,
            repo_type="dataset",
            filename=filename,
            local_dir=str(HF_DIR),
        )
        path = Path(local)
        print(f"  -> {path} ({path.stat().st_size} bytes)", flush=True)
        paths.append(path)
    return paths


def _rmtree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        except OSError:
            continue
    shutil.rmtree(path, ignore_errors=True)


def extract_kept(tars: list[Path], dest: Path) -> tuple[int, int]:
    img_dir = dest / "images" / "train"
    lbl_dir = dest / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    existing = sum(1 for p in img_dir.iterdir() if p.suffix in IMAGE_EXT)
    if existing > 1000:
        n_lbl = sum(1 for p in lbl_dir.iterdir() if p.suffix.lower() == ".txt")
        print(f"reusing {existing} already extracted HF images, {n_lbl} labels", flush=True)
        return existing, n_lbl
    n_img = n_lbl = 0
    for tar_path in tars:
        print(f"extracting kept members from {tar_path.name}", flush=True)
        with tarfile.open(tar_path, "r:gz") as tf:
            for member in tf:
                if not member.isfile():
                    continue
                base = Path(member.name.replace("\\", "/")).name
                if not _keep(base):
                    continue
                suffix = Path(base).suffix
                if suffix in IMAGE_EXT:
                    out = img_dir / base
                    kind = "img"
                elif suffix.lower() == ".txt":
                    out = lbl_dir / base
                    kind = "lbl"
                else:
                    continue
                if out.exists():
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                out.write_bytes(src.read())
                if kind == "img":
                    n_img += 1
                else:
                    n_lbl += 1
                if (n_img + n_lbl) % 200 == 0:
                    print(f"  kept so far images={n_img} labels={n_lbl}", flush=True)
    print(f"HF kept images={n_img} labels={n_lbl}")
    return n_img, n_lbl


def _copy_split(split: str, dest: Path) -> int:
    img_src = INDIA / "images" / split
    lbl_src = INDIA / "labels" / split
    n = 0
    for img in img_src.iterdir():
        if img.suffix not in IMAGE_EXT:
            continue
        _link_or_copy(img, dest / "images" / split / img.name)
        lbl = lbl_src / f"{img.stem}.txt"
        if lbl.is_file():
            _link_or_copy(lbl, dest / "labels" / split / lbl.name)
        n += 1
    return n


def _country_ok(name: str, countries: tuple[str, ...] | None) -> bool:
    if not countries:
        return True
    return any(name.startswith(f"rdd_{country}_") for country in countries)


def _has_cls(lbl: Path, cls_id: int) -> bool:
    try:
        lines = lbl.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return any(ln.strip().startswith(f"{cls_id} ") for ln in lines if ln.strip())


def _select_extras(
    hf_kept: Path,
    *,
    countries: tuple[str, ...] | None,
    max_extra: int | None,
    seed: int,
) -> list[Path]:
    img_dir = hf_kept / "images" / "train"
    lbl_dir = hf_kept / "labels" / "train"
    items: list[Path] = []
    for img in img_dir.iterdir():
        if img.suffix not in IMAGE_EXT:
            continue
        if not _country_ok(img.name, countries):
            continue
        lbl = lbl_dir / f"{img.stem}.txt"
        if not lbl.is_file() or not lbl.read_text(encoding="utf-8").strip():
            continue
        items.append(img)
    rng = random.Random(seed)
    rng.shuffle(items)
    d10 = [img for img in items if _has_cls(lbl_dir / f"{img.stem}.txt", 1)]
    rest = [img for img in items if img not in set(d10)]
    ordered = d10 + rest
    if max_extra is not None:
        ordered = ordered[: max(0, max_extra)]
    return ordered


def build_mix(
    hf_kept: Path,
    *,
    dest: Path = MIX,
    countries: tuple[str, ...] | None = None,
    max_extra: int | None = None,
    seed: int = 42,
) -> Path:
    _rmtree(dest)
    train_n = _copy_split("train", dest)
    val_n = _copy_split("val", dest)
    test_n = _copy_split("test", dest)
    extra = 0
    for img in _select_extras(hf_kept, countries=countries, max_extra=max_extra, seed=seed):
        lbl = hf_kept / "labels" / "train" / f"{img.stem}.txt"
        _link_or_copy(img, dest / "images" / "train" / img.name)
        _link_or_copy(lbl, dest / "labels" / "train" / lbl.name)
        extra += 1
    yaml = dest / "data.yaml"
    yaml.write_text(
        "\n".join(
            [
                f"path: {dest.resolve().as_posix()}",
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
    print(
        f"mix yaml={yaml} india_train={train_n} hf_extra={extra} "
        f"val={val_n} test={test_n} countries={countries or 'all-kept'} "
        f"(val/test frozen India)"
    )
    return yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Mix HF RDD extras into frozen India val/test")
    parser.add_argument(
        "--countries",
        default="",
        help="Comma list of RDD countries to mix (e.g. China_MotorBike). Empty = all kept prefixes.",
    )
    parser.add_argument("--max-extra", type=int, default=0, help="Cap extras. 0 = no cap.")
    parser.add_argument("--mix-dir", default="", help="Output mix folder under repo or absolute.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not (INDIA / "images" / "test").is_dir():
        print("missing .data/rdd_india — run scripts/prepare_rdd_india.py first", file=sys.stderr)
        return 2
    kept = HF_DIR / "kept"
    kept_imgs = kept / "images" / "train"
    if kept_imgs.is_dir() and sum(1 for p in kept_imgs.iterdir() if p.suffix in IMAGE_EXT) > 1000:
        print(f"reusing extracted HF kept at {kept}", flush=True)
    else:
        tars = download_tars()
        extract_kept(tars, kept)
    dest = Path(args.mix_dir) if args.mix_dir else MIX
    if not dest.is_absolute():
        dest = ROOT / dest
    countries = tuple(c.strip() for c in args.countries.split(",") if c.strip()) or None
    max_extra = args.max_extra if args.max_extra > 0 else None
    build_mix(kept, dest=dest, countries=countries, max_extra=max_extra, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
