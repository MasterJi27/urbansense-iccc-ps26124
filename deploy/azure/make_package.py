"""Build the Azure App Service zip for the backend (the API plus the built dashboard and /field).

Run it through deploy/azure/package-azure.bat, which builds the dashboard and runs the tests first.

The zip root is the contents of backend/, which is what the App Service startup command expects
(`python -m uvicorn app.main:app`). Azure then installs requirements.txt itself (SCM_DO_BUILD_DURING_DEPLOYMENT).
Only an allowlist goes in. Secrets and local state (.env, *.db, .venv, tests) can never end up in the package, and the
script refuses to write the zip if one of them slips in or if something the app needs is missing.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUT_DIR = ROOT / "dist" / "azure"

INCLUDE_DIRS = ["app", "alembic", "models", "static_dash"]
INCLUDE_FILES = ["alembic.ini", "requirements.txt", "scripts_migrate.py"]
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".git"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".db", ".sqlite", ".log")
FORBIDDEN_PARTS = {".env", ".venv", "venv", "tests", "node_modules", ".git"}
REQUIRED = ["app/main.py", "requirements.txt", "static_dash/index.html", "app/weights/rdd_india.onnx", "alembic.ini"]
APP_NAME = "app-urbansense-yngmbk"
RESOURCE_GROUP = "rg-urbansense"


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def collect() -> list[Path]:
    found: list[Path] = []
    for name in INCLUDE_FILES:
        path = BACKEND / name
        if path.is_file():
            found.append(path)
    for folder in INCLUDE_DIRS:
        base = BACKEND / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel_parts = set(path.relative_to(BACKEND).parts)
            if not path.is_file() or rel_parts & SKIP_DIRS or path.name.endswith(SKIP_SUFFIXES) or path.name.startswith(".env"):
                continue
            found.append(path)
    return found


def main() -> int:
    files = collect()
    names = [p.relative_to(BACKEND).as_posix() for p in files]

    missing = [r for r in REQUIRED if r not in names]
    if missing:
        print("[x] Not packaged. Missing from backend/: " + ", ".join(missing), file=sys.stderr)
        if "static_dash/index.html" in missing:
            print("    Build the dashboard first: scripts\\build-ui.bat", file=sys.stderr)
        return 1
    leaked = [n for n in names if FORBIDDEN_PARTS & set(n.split("/")) or n.endswith((".db", ".sqlite"))]
    if leaked:
        print("[x] Not packaged. Forbidden files in the package: " + ", ".join(leaked[:5]), file=sys.stderr)
        return 1
    if (BACKEND / "app" / "weights" / "rdd_india.onnx").stat().st_size < 1_000_000:
        print("[x] Not packaged. backend/app/weights/rdd_india.onnx looks like a placeholder (under 1 MB).", file=sys.stderr)
        return 1

    commit = git("rev-parse", "--short", "HEAD") or "unknown"
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    stamp = time.strftime("%Y%m%d-%H%M")
    info = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit": commit + ("+uncommitted-changes" if dirty else ""),
        "files": len(files),
        "target": {"app": APP_NAME, "resource_group": RESOURCE_GROUP, "runtime": "PYTHON|3.12"},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / f"sadaksaarthi-api-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, name in zip(files, names):
            zf.write(path, name)
        zf.writestr("build_info.json", json.dumps(info, indent=2))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OUT_DIR / (zip_path.name + ".sha256")).write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    with zipfile.ZipFile(zip_path) as zf:
        assert zf.testzip() is None, "zip is corrupt"
        assert "app/main.py" in zf.namelist()

    print()
    print(f"Azure package ready: {zip_path}")
    print(f"  size {zip_path.stat().st_size / 1e6:.1f} MB | {len(files)} files | commit {info['git_commit']}")
    print(f"  sha256 {digest}")
    if dirty:
        print("  [!] There are uncommitted changes. The zip contains your working tree, not the last commit.")
    print()
    print("Deploy it (this script never deploys). Either:")
    print(f"  az webapp deploy --resource-group {RESOURCE_GROUP} --name {APP_NAME} --src-path \"{zip_path}\" --type zip")
    print("or, from the project root, let azd package and deploy it itself:  azd deploy api")
    print("Check it afterwards:  https://" + APP_NAME + ".azurewebsites.net/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
