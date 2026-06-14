#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reassemble split large artifacts after cloning the repository."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "large_artifacts" / "split"
OUT = ROOT / "restored_large_artifacts"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    main()
