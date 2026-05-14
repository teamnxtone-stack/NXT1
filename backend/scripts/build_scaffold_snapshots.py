"""Bake scaffold snapshots from the live scaffold packs.

Run from /app/backend (or anywhere — the script resolves paths relative
to itself):

    python3 scripts/build_scaffold_snapshots.py
    python3 scripts/build_scaffold_snapshots.py --kinds nextjs-tailwind expo-rn
    python3 scripts/build_scaffold_snapshots.py --clean

Output: /app/backend/scaffold_snapshots/<kind>.tar.gz, one per pack kind.

Why
---
The runtime project-create path prefers a baked snapshot over the live
generator (see services/scaffold_snapshot_service.py). Snapshots stay
regenerable from the packs in services/scaffolds/, so we never drift —
this script is the single source of truth for keeping them in sync.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make `services.*` imports work when run via `python scripts/...`
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import scaffolds as scaffolds_pack
from services.scaffold_snapshot_service import (
    NAME_SENTINEL,
    bake_snapshot,
    snapshot_dir,
)


def bake_one(kind: str, dest: Path) -> dict:
    t0 = time.perf_counter()
    files = scaffolds_pack.build_scaffold(kind, project_name=NAME_SENTINEL)
    out = bake_snapshot(kind, dest, files)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    size_kb = round(out.stat().st_size / 1024, 1)
    print(f"  ✓ {kind:<22} → {out.name:<32} "
          f"({len(files)} files, {size_kb} KB, {elapsed} ms)")
    return {"kind": kind, "file_count": len(files), "size_kb": size_kb}


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake NXT1 scaffold snapshots")
    ap.add_argument("--kinds", nargs="*", default=None,
                    help="Subset of kinds to bake (default: all)")
    ap.add_argument("--clean", action="store_true",
                    help="Delete existing snapshots before baking")
    args = ap.parse_args()

    dest = snapshot_dir()
    dest.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for old in dest.glob("*.tar.gz"):
            old.unlink()
            print(f"  ✗ removed {old.name}")

    kinds = args.kinds or scaffolds_pack.pack_kinds()
    print(f"Baking {len(kinds)} scaffold snapshot(s) → {dest}")
    results = [bake_one(k, dest) for k in kinds]
    total_size = sum(r["size_kb"] for r in results)
    print(f"\nDone. {len(results)} snapshots · {round(total_size, 1)} KB total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
