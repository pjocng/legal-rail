"""
The Legal Rail -- data pipeline build step.

Reads every file in data/sources/*.json (one per adapter), validates each
against data/schema/observation.schema.json, and merges them into:

  data/merged/observations.json  -- every observation, concatenated
  data/merged/summary.json       -- one "latest" row per (metric_id, scope,
                                     state) combination, plus a derived
                                     `flag` for anything with a statutory
                                     days-in-custody ceiling. This is the
                                     only file the dashboard (demo.html)
                                     reads.

Adding a new source means: write an adapter that outputs a file matching
the observation schema into data/sources/, then run this script. Nothing
else changes -- not the schema, not the dashboard, not this script.

Usage:
    python build.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "adapters"))
from validate import validate_observations, validate_sources_registry  # noqa: E402

ROOT = Path(__file__).resolve().parent
SOURCES_DIR = ROOT / "data" / "sources"
MERGED_DIR = ROOT / "data" / "merged"

STATUTORY_LIMIT_DAYS = 180  # ACJA 2015's ceiling for a Magistrate-court trial to conclude


def load_all_observations():
    registry = json.loads((ROOT / "data" / "sources_registry.json").read_text(encoding="utf-8"))
    validate_sources_registry(registry)
    registry_by_id = {s["id"]: s for s in registry}

    all_obs = []
    for f in sorted(SOURCES_DIR.glob("*.json")):
        obs = json.loads(f.read_text(encoding="utf-8"))
        validate_observations(obs, source_label=f.name)
        for o in obs:
            if o["source_id"] not in registry_by_id:
                raise ValueError(f"{f.name}: source_id '{o['source_id']}' is not in data/sources_registry.json")
        all_obs.extend(obs)
        print(f"  loaded {len(obs):>3} observations from {f.name}")
    return all_obs, registry_by_id


def build_summary(observations):
    """One latest row per (metric_id, scope, state) -- the smallest shape a
    dashboard needs, with weaker-confidence data never silently overwriting
    stronger-confidence data for the same key."""
    def key(o):
        return (o["metric_id"], o["scope"], o.get("state"))

    best = {}
    for o in observations:
        k = key(o)
        current = best.get(k)
        if current is None:
            best[k] = o
            continue
        # Prefer: better confidence tier, then more recent period, then more recently fetched.
        better_confidence = o["confidence_tier"] < current["confidence_tier"]
        same_confidence = o["confidence_tier"] == current["confidence_tier"]
        more_recent_period = o["period"] > current["period"]
        more_recent_fetch = o["fetched_at"] > current["fetched_at"]
        if better_confidence or (same_confidence and (more_recent_period or (o["period"] == current["period"] and more_recent_fetch))):
            best[k] = o

    summary_rows = list(best.values())

    # Derive a statutory-timeline flag wherever we have days-in-custody data.
    for row in summary_rows:
        if row["metric_id"] == "median_days_in_custody" and row["unit"] == "days":
            days = row["value"]
            if days > STATUTORY_LIMIT_DAYS:
                flag = "breach"
            elif days >= STATUTORY_LIMIT_DAYS * 0.85:
                flag = "at_risk"
            else:
                flag = "on_track"
            row["derived_flag"] = flag
            row["statutory_limit_days"] = STATUTORY_LIMIT_DAYS

    return summary_rows


def main():
    print("Loading sources...")
    observations, registry_by_id = load_all_observations()
    print(f"Total: {len(observations)} observations from {len(registry_by_id)} registered sources")

    MERGED_DIR.mkdir(parents=True, exist_ok=True)

    obs_sorted = sorted(observations, key=lambda o: (o["metric_id"], o["scope"], o.get("state") or "", o["period"]))
    (MERGED_DIR / "observations.json").write_text(json.dumps(obs_sorted, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MERGED_DIR / 'observations.json'}")

    summary = build_summary(observations)
    summary_sorted = sorted(summary, key=lambda o: (o["metric_id"], o["scope"], o.get("state") or ""))
    live_sources = sum(1 for s in registry_by_id.values() if s["access"] == "open" and s["status"] == "active")
    pending_sources = sum(1 for s in registry_by_id.values() if s["access"] == "gated_pending_mou")
    output = {
        "generated_at": obs_sorted[-1]["fetched_at"] if obs_sorted else None,
        "live_sources": live_sources,
        "pending_sources": pending_sources,
        "total_sources": live_sources + pending_sources,
        "rows": summary_sorted,
    }
    (MERGED_DIR / "summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MERGED_DIR / 'summary.json'} ({len(summary_sorted)} summary rows)")


if __name__ == "__main__":
    main()
