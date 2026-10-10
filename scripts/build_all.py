"""Prepare the runtime context layer. Nothing is pre-built: a GLID's seller.md / buyer.md is created only
when it is used (a call or chat starts, or /api/context/runtime/<glid> is requested).

This script only:
  1. builds the CSV byte-offset index (data/csv_index.pkl, ~1.5 s) so the pipeline can read one GLID's rows fast
  2. warms the live-API snapshot cache for the featured GLIDs (Global Context + products listing), so their
     first call is instant and they still work offline if the API token has expired

    .venv/bin/python scripts/build_all.py            # index + live snapshots for FEATURED
    .venv/bin/python scripts/build_all.py --no-api   # index only
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import FEATURED  # noqa: E402
from context_layer import catalog_api, csv_index, gc_api  # noqa: E402


def main(use_api=True):
    t0 = time.time()
    csv_index.build()
    if use_api:
        for g in FEATURED:
            for name, fetch, save in (("Global Context", gc_api.fetch, gc_api.save), ("products listing", catalog_api.fetch, catalog_api.save)):
                try:
                    snap = fetch(g)
                    save(g, snap)
                    print(f"{g} {name}: ok")
                except Exception as e:
                    print(f"{g} {name}: FAILED ({str(e)[:80]}) – the last saved snapshot, if any, will be used")
    print(f"done in {time.time() - t0:.1f}s – context files are built at runtime")


if __name__ == "__main__":
    main(use_api="--no-api" not in sys.argv)
