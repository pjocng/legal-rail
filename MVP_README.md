# The Legal Rail — data pipeline

This is the Phase 1 MVP's backend: a small, boring, cheap pipeline that
feeds [`demo.html`](demo.html) real numbers today, and is built so that a
CIMS or state-court data-sharing agreement is a *plug-in*, not a rebuild.

No server runs anywhere. Everything is a JSON file committed to this repo,
built by a script, served as a static file by GitHub Pages.

## How it fits together

```
data/sources/*.json  →  build.py  →  data/merged/summary.json  →  demo.html
   (one file per          (validates,        (the only file            (fetches it,
    adapter)               merges,             the dashboard             fills in the
                            picks the           reads)                    KPI tiles)
                            best-confidence
                            value per metric)
```

- **`data/schema/`** — the target shape. `observation.schema.json` is what
  every metric looks like, from every source, forever. `case.schema.json`
  and `status_event.schema.json` describe the Phase 2/3 rail itself (a
  case's Case Reference Number, and the status pushes each institution
  makes to it) — both are empty today (`data/cases/*.json` are `[]`), but
  the shape exists now so onboarding a real case-level source later means
  filling in rows, not redesigning the model.

- **`data/sources_registry.json`** — the participant registry for *data*,
  mirroring the rail architecture's own "participant registry" component.
  Every source, real or pending, is listed here with its `access` status —
  `open`, `gated_pending_mou`, or `test_fixture`.

- **`adapters/`** — one file per source. An adapter's only job is: fetch
  (or, for manual sources, accept) data and emit a list of objects matching
  `observation.schema.json`. Nothing downstream — `build.py`, `demo.html`
  — ever needs to know a source's original format.

  - `world_prison_brief.py` — a real, tested scraper. Confirmed live
    against the site's actual HTML structure (Aug 2026): the "current
    stats" table is unambiguous label→value→date rows, so those are
    scraped fresh every run. The 2000–2020 historical trend is recorded by
    hand once (see the module docstring for why — the live page packs five
    years into one unseparated string, which isn't safe to auto-split).
  - `nhrc_manual.py` — NHRC publishes as a monthly PDF, not structured
    data, so this isn't a scraper. It's a validated, repeatable *procedure*:
    `python adapters/nhrc_manual.py --add --value 66.0 --period 2026-08 --fetched-by "name"`
    appends one observation after reading the latest dashboard PDF by hand.
  - Adding a new source means writing one new file here in this same
    shape. That's the entire "plug in a new source" story.

- **`build.py`** — loads every file in `data/sources/`, validates each
  against the schema, and merges them into:
  - `data/merged/observations.json` — everything, concatenated.
  - `data/merged/summary.json` — one *latest* row per (metric, scope,
    state), picking the best available confidence tier rather than
    whichever source happened to run most recently. This is the only file
    `demo.html` reads.

- **`.github/workflows/update-data.yml`** — runs the World Prison Brief
  scraper monthly (matching its own publishing cadence) and **opens a pull
  request, never auto-merges**. A human reviews every data change before
  it reaches the live dashboard — the QA checkpoint the pipeline needs
  without a full-time maintainer watching it.

## The confidence-tier system

Every observation carries a `confidence_tier`. This is a structural field
on the data, not a caption on a chart, specifically so it can't quietly
erode as more sources get added over the next two years:

| Tier | Meaning |
|---|---|
| 1 | Live/automated, sourced, national (World Prison Brief) |
| 2 | Manual entry, sourced (NHRC monthly PDF) |
| 3 | Modeled/estimated |
| 4 | Illustrative/sample only — must never be presented as real |

`build.py`'s merge step always prefers a better tier over a worse one for
the same metric, even if the worse-tier source ran more recently.

## Proof the "plug-in" architecture actually works

`data/sources/test_mock_state_feed.json` is not a real source — it's a
fixture shaped like what a CIMS or state-court feed will eventually look
like (state-scoped, monthly, `awaiting_trial_count` and
`median_days_in_custody`). Running it through the same `build.py` as the
real sources, with no schema change and no code change, proves two things
at once: the pipeline generalizes past national-aggregate data, and the
statutory-flag logic (`on_track` / `at_risk` / `breach` against the ACJA's
180-day ceiling) derives correctly once days-in-custody data exists at
all — which is exactly the capability Phase 2 needs from a real CIMS feed.

Delete `test_mock_state_feed.json` and its `sources_registry.json` entry
whenever a real state/facility source replaces it — it isn't meant to ship
as part of the actual dashboard's data mix long-term. It's here to
demonstrate the pipeline's extensibility today, at the point where an
external reviewer (or a future contributor) needs proof it works, not just
a claim that it will.

## When a CIMS (or state-court) MOU comes through

1. Write `adapters/cims.py` (or similar) that authenticates and pulls
   whatever CIMS actually exposes, emitting `observation.schema.json`-shaped
   records — same pattern as `world_prison_brief.py`, most likely
   `scope: "state"` or `"facility"` with `confidence_tier: 1`.
2. Update its `sources_registry.json` entry: `"access": "open"`,
   `"status": "active"`.
3. Once case-level identifiers exist, start populating `data/cases/cases.json`
   and `data/cases/status_events.json` against the schemas already defined
   in `data/schema/` — this is the actual Phase 2/3 rail, and the shape
   has been sitting ready since Phase 1.
4. Remove `test_mock_state_feed.json` if it's still present.

Nothing else changes. `build.py`, `demo.html`, and the schema stay exactly
as they are today.

## Running it locally

```bash
pip install -r requirements.txt
python adapters/world_prison_brief.py   # re-scrape the live page
python adapters/validate.py             # validate every committed data file
python build.py                         # rebuild data/merged/
python -m http.server 8000              # then open demo.html — fetch() needs http://, not file://
```
