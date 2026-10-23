"""Runtime settings (from the environment) and every analytics constant in one place."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings. Override with CFC_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="CFC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cfcoach:cfcoach@localhost:5433/cfcoach"
    cf_base_url: str = "https://codeforces.com/api"
    user_agent: str = "cf-coach/0.1 (+https://github.com/sifat-hossain-niloy/cf-coach; public training dashboard)"
    # Trust X-Real-IP from a reverse proxy (nginx in docker-compose). Off when exposed directly.
    trust_proxy: bool = False
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- Codeforces client -----------------------------------------------------------------------
CF_MIN_INTERVAL_S = 2.1          # global minimum gap between any two Codeforces requests
CF_MAX_RETRIES = 5               # retries after the first attempt
CF_BACKOFF_BASE_S = 2.0          # backoff = base * 2**attempt (+ the limiter gap)
CF_BACKOFF_MAX_S = 60.0
CF_TIMEOUT_S = 30.0
CF_STATUS_PAGE_SIZE = 1000       # user.status page size
CF_USER_INFO_BATCH = 10000       # documented max handles per user.info call

# --- Sync / caching ----------------------------------------------------------------------------
SYNC_FRESH_MINUTES = 10          # don't re-sync a handle more often than this
NOT_FOUND_CACHE_MINUTES = 10     # remember "handle not found" this long
PROBLEMSET_MAX_AGE_HOURS = 24    # problemset.problems refreshed once per day
IP_SYNC_LIMIT_PER_HOUR = 10      # per-IP sync requests (that actually enqueue) per hour
HANDLE_PATTERN = r"^[A-Za-z0-9_.\-]{3,24}$"

# --- Data rules --------------------------------------------------------------------------------
GYM_CONTEST_MIN_ID = 100000      # contestId >= this is gym → ignored
SPECIAL_TAG = "*special"
DEDUP_MAX_RATING_DIFF = 200      # parallel-round copies must have ratings this close (or missing)
IN_CONTEST_TYPES = frozenset({"CONTESTANT", "OUT_OF_COMPETITION", "VIRTUAL"})
IGNORED_VERDICTS_FOR_ATTEMPTS = frozenset({"COMPILATION_ERROR", "SKIPPED", "TESTING", None})

# --- Level / practice rating ------------------------------------------------------------------
PRACTICE_WINDOW = 30             # last N distinct solved (rated) problems
PRACTICE_PERCENTILE = 75
MIN_RATED_SOLVES_FOR_LEVEL = 10
DEFAULT_LEVEL = 1000

# --- Weakness ---------------------------------------------------------------------------------
TARGET_BAND_LO_OFFSET = 100      # band = [level + lo, level + hi]
TARGET_BAND_HI_OFFSET = 400
WEAKNESS_SMOOTHING_A = 3.0       # a in (solved + a*prior) / (attempted + a)
WEAKNESS_COVERAGE_FULL = 10      # coverage = min(1, solved_in_band / this)
WEAKNESS_COVERAGE_WEIGHT = 0.5
WEAKNESS_FALLBACK_PRIOR = 0.5    # prior when the user has no attempts at all
WEAKNESS_TOP_N = 8

# --- Progress ---------------------------------------------------------------------------------
PROGRESS_RECENT_CONTESTS = 10

# --- Queue ------------------------------------------------------------------------------------
QUEUE_DEFAULT_N = 5
QUEUE_MAX_N = 20
QUEUE_MIX = (("A", 1), ("B", 2), ("C", 2))   # default source mix, in fallback priority order
QUEUE_A_RANGE = (-200, 400)      # attempted-unsolved, relative to level
QUEUE_B_MAX_OFFSET = 500         # unsolved problems from user's contests, up to level + this
QUEUE_C_TOP_TAGS = 4             # draw source C from this many top weak tags
QUEUE_POOL_SIZE = 25             # deterministic random pick from the best N candidates per source

# --- Analytics bookkeeping --------------------------------------------------------------------
MIN_SUBMISSIONS_FOR_DATA = 5     # below this a section reports "not enough data yet"
ANALYTICS_VERSION = 1            # bump to invalidate analytics_cache payloads
