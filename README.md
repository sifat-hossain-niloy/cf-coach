# CF Coach

A public Codeforces training coach. Enter a handle and get a personal dashboard: weak tags, rating-band
analysis, a daily upsolve queue, and progress toward the next rank. Everything comes from the public
Codeforces API. No account is needed.

> Not affiliated with Codeforces.

## Quick start

```bash
docker compose up --build
```

Open <http://localhost:8080> and try `/u/tourist`.

| service    | what it does                                                            | port                          |
|------------|-------------------------------------------------------------------------|-------------------------------|
| `db`       | PostgreSQL 16                                                           | `5433` on the host            |
| `backend`  | FastAPI; runs `alembic upgrade head` on start                           | `127.0.0.1:8000` (dev only)   |
| `worker`   | the only process that talks to Codeforces                               | none                          |
| `frontend` | nginx serving the built React app and proxying `/api` to the backend    | `8080`                        |

### Local development (without containers for app code)

```bash
docker compose up -d db                       # Postgres on localhost:5433
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload       # API on :8000
.venv/bin/python -m app.worker                # in a second terminal
cd ../frontend && npm install && npm run dev  # UI on :5173, proxies /api to :8000
```

### Tests

```bash
cd backend && .venv/bin/pytest          # 81 tests, SQLite in memory, recorded fixtures, never the live API
cd frontend && npm test                 # vitest: queue marks, sync staleness, ranks
```

### Regenerating frontend API types

```bash
cd backend && .venv/bin/python scripts/export_openapi.py   # writes backend/openapi.json
cd ../frontend && npm run gen:types                        # writes src/api/schema.ts
```

## Architecture

```
browser ──► nginx (static + /api proxy) ──► FastAPI ──► PostgreSQL ◄── worker ──► codeforces.com/api
                                             (reads, enqueues)        (jobs table)   (2.1 s global limiter)
```

* **Web requests never call Codeforces.** `POST /api/handles/{h}/sync` enqueues a job in the `jobs` table
  and returns its id and place in line. The frontend polls `GET /api/jobs/{id}` ("You are #3 in line",
  "Fetching submissions (page 2)") and reloads the sections when the job finishes.
* **One worker, one rate limiter.** The worker takes a Postgres advisory lock at startup. Any extra worker
  waits on standby and takes over only if the active one dies. The active worker owns the single
  `RateLimiter`, which keeps at least 2.1 s between any two Codeforces requests, retries included.
  It retries "Call limit exceeded", timeouts, and 5xx responses (Codeforces sometimes answers with
  plain-text 502 pages) with exponential backoff, up to 5 retries.
* **Job dedup.** A partial unique index allows only one queued or running sync per handle. Concurrent
  enqueues that race get the existing job back.
* **Caching.** A handle synced less than 10 minutes ago is not re-synced. "Handle not found" is remembered
  for 10 minutes and returns a clean 404. Sync requests that would create a job are limited to 10 per IP
  per hour, stored in the DB (nginx sets `X-Real-IP`; the backend trusts it only when `CFC_TRUST_PROXY=true`).
* **Incremental submissions.** `user.status` is paged 1000 at a time, newest first, and paging stops at the
  first known submission id. Submissions still being judged are re-fetched on the next sync.
* **Shared problemset.** `problemset.problems` is fetched at most once a day for everyone. Per-(rating bucket,
  tag) counts are precomputed alongside it, so tag importance for any band costs a dictionary lookup.
* **Analytics** are pure functions in `backend/app/analytics/`. They run after each sync and are cached in
  `analytics_cache` as JSON. The queue is computed per request from stored data (no API calls).

### Layout

```
backend/app/
  config.py          every tunable constant (rate limit, weakness constants, queue mix, ...)
  cf/                Codeforces client + global rate limiter
  jobs.py worker.py  job queue + the single worker
  sync.py            one sync: user.info → user.rating → user.status pages → problemset → analytics
  analytics/         dedup, tag/band stats, weakness, practice rating, progress (pure)
  queue.py           daily upsolve queue (pure)
  api/routes.py      HTTP endpoints
frontend/src/
  api/               generated OpenAPI types + typed fetch client
  lib/               marks (localStorage), sync/poll hooks, ranks, formatting
  pages/ components/ landing page, dashboard, charts
```

## API

| method | path | notes |
|---|---|---|
| POST | `/api/handles/{handle}/sync` | `{cached, job}`; 404 if the handle doesn't exist, 429 if over the IP limit |
| GET | `/api/jobs/{id}` | status (`queued`/`running`/`done`/`failed`), `position`, `stage`, `error`, `error_code` |
| GET | `/api/handles/{handle}/summary?target=` | profile, rank, level, target, gap, top 3 weak tags, last synced |
| GET | `/api/handles/{handle}/tags` | per-tag stats |
| GET | `/api/handles/{handle}/bands` | per-100-point band stats, in-contest vs practice |
| GET | `/api/handles/{handle}/weak?band_lo=&band_hi=` | top 8 weak tags with every score component |
| GET | `/api/handles/{handle}/progress?target=` | rating history, recent pace, rough estimate, practice rating timeline |
| GET | `/api/handles/{handle}/queue?date=YYYY-MM-DD&n=5&exclude=1700-C,1701-A` | daily queue |
| GET | `/api/health` | |

Interactive docs: <http://localhost:8000/docs>.

## How the numbers are computed

### Data rules
* Gym submissions (`contestId >= 100000`) and problems tagged `*special` are ignored.
* A problem is solved if any submission is `OK`. Problems are identified by `(contestId, index)`.
* **Div1/Div2 parallel rounds:** two problems are the same problem when they share a name, their contestIds
  differ by exactly 1, and their ratings are within 200 (or one is unrated). See "Deviations" below.
* Compilation errors, skipped, and still-in-queue submissions don't count as attempts.
* In-contest = `CONTESTANT`, `OUT_OF_COMPETITION` or `VIRTUAL`. Everything else is practice.
* Unrated problems count for tag stats, but not for bands, weakness, or practice rating.

### Level and target
* **Level** = contest rating if the user has rated contests. Otherwise it is the practice rating (with at
  least 10 rated solves), otherwise 1000. The UI says which one applies.
* **Target** = the next rank threshold above the current rating (Pupil 1200, Specialist 1400, Expert 1600,
  CM 1900, Master 2100, IM 2300, GM 2400, IGM 2600, LGM 3000). It can be overridden in the UI. A target above
  level + 400 also widens the weak-tag band up to the target.
* **Practice rating** = the 75th percentile (linear interpolation) of the ratings of the last 30 distinct
  solved problems, tracked after every solve (one point per day).
* **Contests needed** = ceil(gap / average delta of the last 10 rated contests). This is shown only as a rough
  estimate, and when the average is ≤ 0 the UI says the gap isn't closing instead of printing a number.

### Weakness score
For the target band `[level + 100, level + 400]`:

```
importance(t) = share of problemset problems rated in the band that carry tag t
success(t)    = (solved_t + a · prior) / (attempted_t + a)        a = 3
                prior = the user's overall solve rate in the band
coverage(t)   = min(1, solved_t / 10)
weakness(t)   = importance(t) · (1 − success(t)) · (1 − 0.5 · coverage(t))
```

`solved_t` and `attempted_t` count only problems in the band. Importance is precomputed once a day for the
whole problemset. The prior falls back to the user's overall solve rate, then to 0.5, for users with no
attempts in the band. The top 8 tags are shown with every component, so the score can be explained. All
constants live in `backend/app/config.py`.

### Daily upsolve queue
Default 5 items: 1 from **A** (attempted, never solved, level − 200 … level + 400), 2 from **B** (unsolved
problems from contests the user took part in, up to level + 500), 2 from **C** (never-attempted problems with
the top weak tags in the target band, preferring a high solvedCount and recent contests). When a source runs
dry, the others fill in (C, then B, then A). Items are ordered easy → hard.

* **Deterministic:** each source's candidates are shuffled with an RNG seeded from `sha256(handle | date |
  source)`, so a refresh shows the same list.
* **Stable during the day:** candidates come from history *before* the queue date. Solving an item today
  marks it ✓ after the next sync instead of swapping it out.
* **Skips** are sent as `exclude`. Picks walk a fixed shuffled order, so skipping replaces only that item.
* **Skip and "needed editorial" marks live in the browser** (localStorage, every access wrapped in try/catch).
  Editorial problems leave the queue and come back as "Review due" 7 and 21 days after marking.

## Compare two handles (stretch goal)

`/compare/{a}/{b}` shows two handles side by side: profile cards, overlaid rating histories, solve rate by
band, and a tag table. It reuses the per-handle endpoints and syncs either handle when it's stale. The
dashboard links to it with a "Compare with…" box. The other stretch goals (handle verification with
server-side marks, and email or Telegram digests) aren't built.

## Deviations from the original brief

* `https://codeforces.com/apiHelp` sits behind a Cloudflare bot check (HTTP 403) and couldn't be read, so field
  names were checked against live API responses instead. They matched the brief. A handle that doesn't
  exist returns HTTP 400 with `{"status":"FAILED","comment":"handles: User with handle … not found"}`, and
  the client maps that to a 404.
* **Parallel-round dedup is stricter than "within 1".** Same-contest problems share names on purpose (E1/E2
  easy/hard versions), so they must not merge. The live problemset also has same-name *different* problems in
  adjacent contests, e.g. 505A and 506E "Mr. Kitayuta's Gift" (rated 1100 vs 3000). So ids must differ by
  exactly 1 and ratings must be within 200.
* Queue source C uses contestId as the "recent contest" proxy, which avoids an extra `contest.list` call.
* Codeforces also reports a rank called `"tourist"` (it is tourist's `maxRank`), which the brief's table
  doesn't include. CF Coach stops at Legendary Grandmaster, so users at 3000+ have no next target unless they
  set one.

## Deploying

The images are production-ready: the backend runs as a non-root user, and the frontend is a static nginx
build with immutable caching for hashed assets. Typical setup:

1. Run Postgres (managed or the compose service) and set `CFC_DATABASE_URL`.
2. Run **one** `backend` service and **one** `worker` service from `backend/Dockerfile`. Extra workers just
   stand by.
3. Put the `frontend` image (or any proxy) in front, and set `CFC_TRUST_PROXY=true` only when that proxy
   overwrites `X-Real-IP`.
4. Don't expose the backend port publicly when `CFC_TRUST_PROXY=true`.
