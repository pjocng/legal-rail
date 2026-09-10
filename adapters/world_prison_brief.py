"""
Adapter: World Prison Brief (Nigeria)
https://www.prisonstudies.org/country/nigeria

Confirmed by direct inspection (Aug 2026): the "current stats" block is a
clean, unambiguous table of label -> value -> as-of-date rows. That's what
this adapter parses live, every run.

The 2000-2020 historical trend row is NOT re-scraped: on the live page it
arrives as five years' figures concatenated into one string per column with
no separator (e.g. "27,95928,36335,00039,69448,606"), which is fine for a
human reading a rendered table but not safe to auto-split without risking a
silently wrong value. Those five years are fixed history and don't change
release to release, so they're recorded here once, by hand, with their
source noted -- and only the *current* "latest" row is re-scraped live,
since that row is always cleanly separated in its own <tr>.

Change detection: every run compares the freshly-scraped figures against
what's already committed. If nothing meaningful moved -- same values, same
periods -- the file is left completely untouched, so `git` sees no diff and
the monthly Action opens no pull request. Only a genuine value change (or an
added/removed data point) rewrites the file and, in CI, produces a
reviewable PR. A run that only re-confirms the same numbers is a no-op, not
noise. `fetched_at` on an unchanged record therefore means "when this value
was last *different*", not "when it was last checked" -- the check history
lives in the Actions run log.

Usage:
    python adapters/world_prison_brief.py [--offline path/to/saved.html]

Writes data/sources/world_prison_brief.json only when something changed
(validated before it's written).
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import validate_observations  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.prisonstudies.org/country/nigeria"
SOURCE_ID = "world_prison_brief"
OUT_PATH = ROOT / "data" / "sources" / "world_prison_brief.json"

# Verified by hand against the live page's five-year trend table, Aug 2026.
# Source: https://www.prisonstudies.org/country/nigeria -- "Pre-trial/remand
# prison population: trend" table. Stable historical data; not re-scraped.
HISTORICAL_PRETRIAL_TREND = [
    {"period": "2000", "value": 62.9},
    {"period": "2005", "value": 74.0},
    {"period": "2010", "value": 72.9},
    {"period": "2015", "value": 69.3},
    {"period": "2020", "value": 73.8},
]


def _parse_number(s):
    return float(s.replace(",", "").replace("%", "").strip())


def _find_stat(soup, label_substring):
    """The 'current stats' table is <tr><td>label</td><td>value<div class="comment">as-of note</div></td></tr>.
    The value is the value cell's own direct text; the as-of note is nested inside it."""
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label_text = cells[0].get_text(strip=True)
            if not label_text.lower().startswith(label_substring.lower()):
                continue
            value_cell = cells[1]
            comment = value_cell.find("div", class_="comment")
            asof_text = comment.get_text(strip=True) if comment else None
            value_cell_copy = BeautifulSoup(str(value_cell), "html.parser")
            comment_copy = value_cell_copy.find("div", class_="comment")
            if comment_copy:
                comment_copy.decompose()
            value_text = value_cell_copy.get_text(strip=True)
            return value_text, asof_text
    return None, None


def _parse_asof_date(as_of_text, fallback):
    """as_of_text looks like 'at 22.6.2026 (national prison administration)'
    or '(30.6.2025)'. Returns an ISO date string, or fallback if unparsable."""
    if not as_of_text:
        return fallback
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", as_of_text)
    if not m:
        return fallback
    d, mo, y = m.groups()
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return fallback


def fetch(offline_path=None):
    if offline_path:
        html = Path(offline_path).read_text(encoding="utf-8", errors="ignore")
    else:
        resp = requests.get(URL, timeout=30, headers={"User-Agent": "legal-rail-mvp/1.0 (research use)"})
        resp.raise_for_status()
        html = resp.text
    return BeautifulSoup(html, "html.parser")


def build_observations(soup):
    today = datetime.now(timezone.utc).date().isoformat()
    observations = []

    total_raw, total_asof = _find_stat(soup, "Prison population total (including")
    pretrial_raw, pretrial_asof = _find_stat(soup, "Pre-trial detainees")
    capacity_raw, capacity_asof = _find_stat(soup, "Official capacity")
    occupancy_raw, occupancy_asof = _find_stat(soup, "Occupancy level")

    fields = [
        ("total_in_custody", "Total in custody, nationwide", "count", total_raw, total_asof),
        ("pretrial_detention_rate", "Pretrial detention share, national", "percent", pretrial_raw, pretrial_asof),
        ("official_capacity", "Official capacity of correctional system", "count", capacity_raw, capacity_asof),
        ("occupancy_rate", "Occupancy vs. official capacity", "percent", occupancy_raw, occupancy_asof),
    ]
    for metric_id, label, unit, raw, asof in fields:
        if raw is None:
            print(f"WARNING: could not find '{label}' on the page -- page layout may have changed", file=sys.stderr)
            continue
        observations.append({
            "metric_id": metric_id,
            "label": label,
            "unit": unit,
            "scope": "national",
            "state": None,
            "facility": None,
            "case_ref": None,
            "value": _parse_number(raw),
            "period": _parse_asof_date(asof, today)[:4],  # year
            "period_type": "point_in_time",
            "source_id": SOURCE_ID,
            "source_url": URL,
            "fetched_at": today,
            "confidence_tier": 1,
            "verified_by": "scraper:world_prison_brief",
            "notes": f"As of {_parse_asof_date(asof, today)}" if asof else None,
        })

    # Historical trend (hand-verified, static -- see module docstring)
    for point in HISTORICAL_PRETRIAL_TREND:
        observations.append({
            "metric_id": "pretrial_detention_rate",
            "label": "Pretrial detention share, national",
            "unit": "percent",
            "scope": "national",
            "state": None,
            "facility": None,
            "case_ref": None,
            "value": point["value"],
            "period": point["period"],
            "period_type": "annual",
            "source_id": SOURCE_ID,
            "source_url": URL,
            "fetched_at": today,
            "confidence_tier": 1,
            "verified_by": "manual:hand-verified-2026-08",
            "notes": "Historical trend point, hand-transcribed from the site's five-year trend table (see adapter docstring for why it isn't auto-parsed).",
        })

    return observations


def _identity(obs):
    """What makes two observations 'the same data point'."""
    return (obs["metric_id"], obs["period"], obs["scope"], obs.get("state"), obs["period_type"])


def _meaningful(obs):
    """The fields that constitute a *real* change. `fetched_at` and `notes`
    (which just carries the source's as-of date) are bookkeeping -- a run that
    only moves those is not a change worth a pull request."""
    return {k: v for k, v in obs.items() if k not in ("fetched_at", "notes")}


def _write_step_summary(text):
    """If running inside GitHub Actions, surface a human-readable status on
    the run's summary page. No-op locally."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def reconcile(fresh, existing):
    """Merge freshly-scraped observations with what's already committed:
    keep an unchanged record exactly as it was (preserving its original
    fetched_at), take the new version of a changed record, and report every
    add / change / removal. Returns (merged_list, changes)."""
    existing_by_id = {_identity(o): o for o in existing}
    fresh_keys = {_identity(o) for o in fresh}
    merged = []
    changes = []

    for new_obs in fresh:
        key = _identity(new_obs)
        old = existing_by_id.get(key)
        if old is None:
            merged.append(new_obs)
            changes.append(f"added   {new_obs['metric_id']} {new_obs['period']} = {new_obs['value']}")
        elif _meaningful(old) != _meaningful(new_obs):
            merged.append(new_obs)
            changes.append(f"changed {new_obs['metric_id']} {new_obs['period']}: {old['value']} -> {new_obs['value']}")
        else:
            merged.append(old)  # unchanged -- keep verbatim, original fetched_at intact

    for old in existing:
        if _identity(old) not in fresh_keys:
            changes.append(f"removed {old['metric_id']} {old['period']} (was {old['value']})")

    return merged, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", help="Parse a saved HTML file instead of fetching live (for testing).")
    args = parser.parse_args()

    soup = fetch(args.offline)
    observations = build_observations(soup)

    if not observations:
        print("ERROR: extracted zero observations -- refusing to overwrite existing data.", file=sys.stderr)
        sys.exit(1)

    validate_observations(observations, source_label=SOURCE_ID)

    existing = []
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    merged, changes = reconcile(observations, existing)

    if existing and not changes:
        print("No change: World Prison Brief figures are identical to the committed data. File left untouched.")
        _write_step_summary("**World Prison Brief:** no change this run — figures identical to committed data.")
        return

    validate_observations(merged, source_label=SOURCE_ID)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(merged)} observations to {OUT_PATH.relative_to(ROOT)}")
    print("Changes:")
    for c in changes:
        print(f"  {c}")
    _write_step_summary("**World Prison Brief:** changes this run:\n\n" + "\n".join(f"- `{c}`" for c in changes))


if __name__ == "__main__":
    main()
