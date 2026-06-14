#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reassemble split large artifacts after cloning the repository."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "large_artifacts" / "split"
FULL_NONMINUTE = ROOT / "large_artifacts" / "full_nonminute"
OUT = ROOT / "restored_large_artifacts"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # Restore one-file artifacts split under large_artifacts/split/.
    for manifest_path in sorted(SPLIT.glob("*/manifest.json")):
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        out_path = OUT / meta["file_name"]
        with out_path.open("wb") as out:
            for part in meta["parts"]:
                out.write((manifest_path.parent / part["name"]).read_bytes())
        digest = sha256(out_path)
        if digest != meta["sha256"]:
            raise SystemExit(f"sha mismatch for {out_path}: {digest} != {meta['sha256']}")
        print(f"restored {out_path} ({out_path.stat().st_size} bytes)")

    # Restore directory-tree artifacts mirrored under full_nonminute/.
    manifest = FULL_NONMINUTE / "FULL_NONMINUTE_MANIFEST.json"
    if manifest.exists():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        full_out = OUT / "full_nonminute"
        full_out.mkdir(parents=True, exist_ok=True)
        for group in meta.get("groups", []):
            for entry in group.get("entries", []):
                if entry.get("kind") != "split_file":
                    continue
                parts_dir = FULL_NONMINUTE / entry["relative_parts_dir"]
                out_path = full_out / entry["relative_output"]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with out_path.open("wb") as out:
                    for part in entry["parts"]:
                        out.write((parts_dir / part["name"]).read_bytes())
                digest = sha256(out_path)
                if digest != entry["sha256"]:
                    raise SystemExit(
                        f"sha mismatch for {out_path}: {digest} != {entry['sha256']}"
                    )
                print(f"restored {out_path} ({out_path.stat().st_size} bytes)")
        print(f"full_nonminute direct files are already present under {FULL_NONMINUTE}")


if __name__ == "__main__":
    main()
