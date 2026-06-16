"""Build runnable ``.aieng`` packages for the analytical FEA benchmark corpus.

Usage:
    python build_packages.py --out-dir build/analytical_fea
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The fixture builder currently lives under aieng/tests/fixtures. Make it
# importable when this script is run from the repo checkout.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
if str(_TESTS_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_TESTS_FIXTURES))

from nafems.build_fixtures import build_all_fixtures  # type: ignore[import-not-found]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build .aieng packages for the analytical FEA benchmark corpus"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build") / "analytical_fea",
        help="Directory to write the .aieng packages to",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = build_all_fixtures(out_dir)
    print(f"Built {len(paths)} packages in {out_dir}")
    for case_id, path in sorted(paths.items()):
        print(f"  {case_id}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
