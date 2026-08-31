"""
Adapter: NHRC Human Rights Situation Dashboard (manual)
https://www.nigeriarights.gov.ng/nhrc-media/data-and-infographics.html

Not a scraper -- confirmed by direct inspection (Aug 2026) that NHRC
publishes this monthly as a PDF/image report, not structured data. This
script does NOT fetch anything. It exists so the manual-entry workflow is a
real, repeatable, validated step -- not an ad hoc edit to a JSON file --
and so a future session (yours, or a prompted one of mine) has an
unambiguous procedure to follow every month:

  1. Open the latest dashboard at the URL above.
  2. Find the pretrial/awaiting-trial detention figure (and any other
     metric worth tracking -- extend METRICS_TO_WATCH below as needed).
  3. Run:  python adapters/nhrc_manual.py --add \
             --value 66.0 --period 2026-08 --fetched-by "your-name"
  4. This appends one validated observation to data/sources/nhrc_dashboard.json.
     It never overwrites prior months -- NHRC data is a time series.

Usage:
    python adapters/nhrc_manual.py --add --value 66.0 --period 2026-08 --fetched-by "name"
    python adapters/nhrc_manual.py --check   # validates the file without adding anything
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_observations  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ID = "nhrc_dashboard"
SOURCE_URL = "https://www.nigeriarights.gov.ng/nhrc-media/data-and-infographics.html"
OUT_PATH = ROOT / "data" / "sources" / "nhrc_dashboard.json"


def load():
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return []


def add_observation(value, period, fetched_by, notes=None):
    existing = load()
    today = datetime.now(timezone.utc).date().isoformat()

    if any(o["period"] == period and o["metric_id"] == "pretrial_detention_rate" for o in existing):
        print(f"ERROR: an observation for period {period} already exists. "
              f"Edit data/sources/nhrc_dashboard.json by hand if you need to correct it.", file=sys.stderr)
        sys.exit(1)

    new_obs = {
        "metric_id": "pretrial_detention_rate",
        "label": "Pretrial detention share, national (NHRC/UNODC)",
        "unit": "percent",
        "scope": "national",
        "state": None,
        "facility": None,
        "case_ref": None,
        "value": value,
        "period": period,
        "period_type": "monthly",
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "fetched_at": today,
        "confidence_tier": 2,
        "verified_by": f"manual:{fetched_by}",
        "notes": notes,
    }
    combined = existing + [new_obs]
    validate_observations(combined, source_label=SOURCE_ID)

    OUT_PATH.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    print(f"Added {period} = {value}% to {OUT_PATH.relative_to(ROOT)} ({len(combined)} total observations)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--add", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--value", type=float)
    parser.add_argument("--period", help="YYYY-MM")
    parser.add_argument("--fetched-by", help="Who read the PDF and entered this.")
    parser.add_argument("--notes")
    args = parser.parse_args()

    if args.check:
        existing = load()
        validate_observations(existing, source_label=SOURCE_ID)
        print(f"OK -- {len(existing)} observations, all valid.")
        return

    if args.add:
        if args.value is None or not args.period or not args.fetched_by:
            parser.error("--add requires --value, --period, and --fetched-by")
        add_observation(args.value, args.period, args.fetched_by, args.notes)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
