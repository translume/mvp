"""Prepare the locked source snapshots inside the Docker build."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/translume-core/src"))

from translume_core.vendor.packaged import install_packaged_vendor_sources


def main() -> int:
    install_packaged_vendor_sources(ROOT)
    print("Verified and installed all three bundled MIMS source snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
