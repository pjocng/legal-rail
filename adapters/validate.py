"""
Shared validation used by every adapter and by build.py.

Every adapter's whole job is: fetch from one source, return a list of dicts
shaped like data/schema/observation.schema.json. Nothing else in the pipeline
should know that source's format exists.
"""
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "data" / "schema"


def _load_schema(name):
    with open(SCHEMA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


OBSERVATION_SCHEMA = _load_schema("observation.schema.json")
SOURCE_SCHEMA = _load_schema("source.schema.json")
CASE_SCHEMA = _load_schema("case.schema.json")
STATUS_EVENT_SCHEMA = _load_schema("status_event.schema.json")


def validate_observations(observations, source_label="unknown"):
    """Validate a list of observation dicts. Raises with a clear message on
    the first failure -- a bad adapter should fail loudly in CI, not ship a
    silently malformed number to the dashboard."""
    if not isinstance(observations, list):
        raise ValueError(f"[{source_label}] expected a list of observations, got {type(observations)}")
    for i, obs in enumerate(observations):
        try:
            jsonschema.validate(instance=obs, schema=OBSERVATION_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(
                f"[{source_label}] observation #{i} failed validation: {e.message}\n"
                f"  offending record: {json.dumps(obs, indent=2)}"
            ) from e
    return True


def validate_sources_registry(sources):
    for i, src in enumerate(sources):
        try:
            jsonschema.validate(instance=src, schema=SOURCE_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(f"sources_registry.json entry #{i} failed validation: {e.message}") from e
    return True


def validate_cases(cases):
    for i, c in enumerate(cases):
        try:
            jsonschema.validate(instance=c, schema=CASE_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(f"cases.json entry #{i} failed validation: {e.message}") from e
    return True


def validate_status_events(events):
    for i, ev in enumerate(events):
        try:
            jsonschema.validate(instance=ev, schema=STATUS_EVENT_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(f"status_events.json entry #{i} failed validation: {e.message}") from e
    return True


if __name__ == "__main__":
    # Quick self-check: validate every committed data file against its schema.
    ok = True
    sources = json.loads((ROOT / "data" / "sources_registry.json").read_text(encoding="utf-8"))
    try:
        validate_sources_registry(sources)
        print(f"OK  sources_registry.json ({len(sources)} sources)")
    except ValueError as e:
        print(f"FAIL  {e}")
        ok = False

    for f in sorted((ROOT / "data" / "sources").glob("*.json")):
        obs = json.loads(f.read_text(encoding="utf-8"))
        try:
            validate_observations(obs, source_label=f.name)
            print(f"OK  {f.relative_to(ROOT)} ({len(obs)} observations)")
        except ValueError as e:
            print(f"FAIL  {e}")
            ok = False

    cases = json.loads((ROOT / "data" / "cases" / "cases.json").read_text(encoding="utf-8"))
    validate_cases(cases)
    print(f"OK  data/cases/cases.json ({len(cases)} cases)")

    events = json.loads((ROOT / "data" / "cases" / "status_events.json").read_text(encoding="utf-8"))
    validate_status_events(events)
    print(f"OK  data/cases/status_events.json ({len(events)} events)")

    sys.exit(0 if ok else 1)
