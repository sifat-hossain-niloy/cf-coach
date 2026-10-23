# CF Coach: build plan

You were away, so I wrote this plan here instead of waiting in plan mode for approval.

## Folder structure

```
cp-coach/
├── docker-compose.yml          # db, backend, worker, frontend
├── .env.example
├── README.md
├── docs/PLAN.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/                # env.py + versions/
│   ├── app/
│   │   ├── config.py           # env settings + ALL analytics constants
│   │   ├── db.py               # engine / session factory
│   │   ├── models.py           # SQLAlchemy 2.0 models
│   │   ├── schemas.py          # Pydantic response models
│   │   ├── ranks.py            # rank thresholds, colors, target selection
│   │   ├── handles.py          # handle validation / normalisation
│   │   ├── cf/
│   │   │   ├── ratelimit.py    # global limiter (injectable clock + sleep)
│   │   │   └── client.py       # Codeforces client, retries, errors
│   │   ├── analytics/
│   │   │   ├── types.py        # plain dataclasses the pure functions use
│   │   │   ├── dedup.py        # parallel-round dedup, solved/attempted sets
│   │   │   ├── tags.py         # tag stats
│   │   │   ├── bands.py        # rating band stats
│   │   │   ├── weakness.py     # weakness score
│   │   │   ├── practice.py     # practice rating + timeline
│   │   │   └── progress.py     # level, rank, contests-needed estimate
│   │   ├── queue.py            # daily upsolve queue (pure)
│   │   ├── jobs.py             # enqueue / dedup / queue position
│   │   ├── sync.py             # one sync job: CF → DB → analytics cache
│   │   ├── worker.py           # single asyncio worker loop
│   │   ├── iplimit.py          # per-IP sync rate limit (DB-backed)
│   │   ├── api/routes.py       # FastAPI routes
│   │   └── main.py             # FastAPI app
│   ├── scripts/                # export_openapi.py, sync_once.py
│   └── tests/
│       ├── fixtures/*.json     # recorded CF responses (trimmed)
│       └── test_*.py
└── frontend/
    ├── Dockerfile + nginx.conf # static build + /api proxy
    ├── src/api/schema.ts       # generated from OpenAPI (openapi-typescript)
    ├── src/lib/                # marks (localStorage), ranks, formatting (+ vitest)
    ├── src/pages/              # Landing, Dashboard
    └── src/components/         # sections + charts
```

## DB schema

| table | key columns |
|---|---|
| `handles` | `id`, `handle_key` (lower-case, unique), `display_handle`, `rating`, `max_rating`, `rank`, `max_rank`, `newest_submission_id`, `last_synced_at`, `not_found_at` |
| `submissions` | `id` (CF submission id, PK), `handle_id`, `contest_id`, `problem_index`, `problem_name`, `problem_rating`, `tags` (JSON), `verdict`, `participant_type`, `creation_time` |
| `rating_changes` | `handle_id`, `contest_id` (PK pair), `contest_name`, `rank`, `old_rating`, `new_rating`, `update_time` |
| `problems` | `contest_id`, `index` (PK pair), `name`, `rating`, `tags` (JSON), `solved_count` |
| `problem_tag_buckets` | `bucket` (rating // 100 * 100), `tag` (PK pair), `count`; tag `__total__` holds bucket totals. Recomputed with every problemset refresh, so it is shared by everyone |
| `meta` | `key`, `value`, `updated_at` (e.g. `problemset_fetched_at`) |
| `analytics_cache` | `handle_id`, `kind` (PK pair), `payload` (JSON), `computed_at` |
| `jobs` | `id`, `kind`, `handle_key`, `status` (queued/running/done/failed), `stage`, `error`, `error_code`, `created_at`, `started_at`, `finished_at`. **Partial unique index** on `(handle_key)` where status in (queued, running) |
| `sync_requests` | `id`, `ip`, `created_at` (per-IP rate limiting) |

## Job / worker design

* `POST /sync` → validate the handle format. If it was synced < 10 min ago, return the cached data. Otherwise check the per-IP limit, then
  `enqueue()`: return the active job for that handle if one exists; else insert. If two inserts race, the partial
  unique index catches it (IntegrityError), and we re-select the existing job.
* Queue position = 1 + number of queued jobs with a smaller id + number of running jobs (0 when running).
* Worker = one asyncio process. On start it takes a Postgres advisory lock, so only one worker ever talks to
  Codeforces, and that worker owns the **one global rate limiter** (≥ 2.1 s between any two requests,
  including retries). It resets `running` jobs left over from a crash, then loops:
  claim the oldest queued job (`FOR UPDATE SKIP LOCKED`), run `sync.run_sync`, and mark it done or failed.
* A sync: `user.info` (gets canonical casing; not found → job failed with `error_code=not_found`, and the
  handle is negative-cached so the API returns 404) → `user.rating` → incremental `user.status` pages
  (count=1000, stop at the first known id) → refresh `problemset.problems` if it is > 24 h old → compute
  analytics → write `analytics_cache`.
* Web requests never call Codeforces.

## Phases (commit after each)

1. compose, schema + Alembic, CF client + limiter, jobs + worker, sync, tests
2. pure analytics + read endpoints, tests
3. queue generation, tests
4. frontend: landing, dashboard, polling, charts, marks in localStorage, vitest
5. README, deployment-ready Dockerfiles

## Deviations / decisions (no answers available, so these are my calls)

* `https://codeforces.com/apiHelp` sits behind a Cloudflare bot challenge (HTTP 403) and I could not read it.
  The API itself works, so I checked field names against live responses (`user.info`, `user.status`,
  `user.rating`, `problemset.problems`). They match what the prompt assumes.
* The API sometimes returns plain-text `502` bodies (not JSON), so those count as retryable 5xx.
* **Parallel-round dedup:** two problems are merged only when their contestIds differ by **exactly 1** (same
  contest = E1/E2 easy/hard versions with the same name, which must stay separate) **and** their ratings are
  within 200 or one is missing. The live problemset has false positives such as 505A "Mr. Kitayuta's Gift"
  (1100) vs 506E with the same name (3000).
* "Recent contests" in queue source C uses contestId as the recency proxy (no extra `contest.list` call).
* Target override in the UI changes target/gap. The weakness band defaults to level+100..level+400 and is also
  overridable through `band_lo`/`band_hi` query parameters.
