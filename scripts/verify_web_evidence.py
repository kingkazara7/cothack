#!/usr/bin/env python3
"""Verify saved public web snapshots against the evidence manifest."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence" / "web" / "manifest.json"


def verify() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    checked = []
    for item in manifest["items"]:
        path = ROOT / item["snapshot"]
        stored = path.read_bytes()
        if path.suffix == ".gz":
            assert hashlib.sha256(stored).hexdigest() == item["snapshot_gzip_sha256"]
            raw = gzip.decompress(stored)
        else:
            raw = stored
        assert len(raw) == item["raw_bytes"]
        assert hashlib.sha256(raw).hexdigest() == item["raw_sha256"]
        checked.append(item["id"])
    return {"verified": len(checked), "ids": checked}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
