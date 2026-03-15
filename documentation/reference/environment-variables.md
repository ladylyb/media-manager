# Environment Variables

This page is the canonical reference for environment configuration used by media-manager.

Defaults below reflect runtime code defaults, not shell defaults.

## Core Connectivity

### `DATABASE_URL`
- Purpose: Primary PostgreSQL connection URL for runtime and migrations.
- Format: `postgresql+psycopg://<user>:<password>@<host>:<port>/<db>`
- Default in code: none (required)
- Example: `postgresql+psycopg://postgres:password@localhost:5432/media_manager`

### `MEDIA_MANAGER_API_HOST`
- Purpose: Bind host for the packaged `media-manager-api` launcher.
- Format: Host or IP string
- Default in code: `127.0.0.1`
- Example: `127.0.0.1`

### `MEDIA_MANAGER_API_PORT`
- Purpose: Bind port for the packaged `media-manager-api` launcher.
- Format: Integer port
- Default in code: `8000`
- Example: `8000`

### `MEDIA_MANAGER_API_RELOAD`
- Purpose: Enable Uvicorn reload mode for the packaged `media-manager-api` launcher.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false`
- Example: `false`

### `TEST_DATABASE_URL`
- Purpose: Dedicated PostgreSQL URL for pytest fixtures and audit tooling.
- Format: `postgresql+psycopg://<user>:<password>@<host>:<port>/<db>`
- Default in code: none (required for tests)
- Example: `postgresql+psycopg://postgres:password@localhost:5432/media_manager_test`
- Precedence: phase audit tooling uses `TEST_DATABASE_URL` first, then `DATABASE_URL`.

## Logging and Metadata

### `LOG_LEVEL`
- Purpose: Application logging verbosity.
- Allowed values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- Default in code: `INFO`
- Example: `INFO`

### `MEDIA_REQUIRED_CODES`
- Purpose: Required metadata code set for planner strictness and validation paths.
- Format: Comma-separated metadata code names.
- Default in code: `OWNER,CONTEXT,TAKEN_DT`
- Example: `OWNER,CONTEXT,TAKEN_DT`

### `MEDIA_MANAGER_TAG_NORMALIZATION_REMOVE_PUNCTUATION`
- Purpose: Toggle punctuation removal in tag normalization.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `0` (disabled)
- Example: `0`

## Canonical Policy Defaults

### `MEDIA_CANONICAL_POLICY`
- Purpose: Default canonical policy before persisted operator settings exist.
- Allowed values: `FIRST_SEEN`, `PREFER_ROOT`, `SHORTEST_PATH`
- Default in code: `FIRST_SEEN`
- Example: `FIRST_SEEN`

### `MEDIA_PREFERRED_ROOTS`
- Purpose: Preferred root list for `PREFER_ROOT` tie-breaking defaults.
- Format: Comma-separated root paths.
- Default in code: empty
- Example: `/Archive,/Media`

## Observability and Performance Tuning

### `MEDIA_MANAGER_METRICS_ENABLED`
- Purpose: Enable Prometheus metric collection and optional server startup.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `0` (disabled)
- Example: `0`

### `MEDIA_MANAGER_METRICS_PORT`
- Purpose: Standalone Prometheus HTTP server port when metrics server is enabled.
- Format: Integer port
- Default in code: `9000`
- Example: `9000`

### `MEDIA_MANAGER_PROMETHEUS_URL`
- Purpose: External Prometheus base URL shown in the Admin observability UI for operator deep links.
- Format: HTTP(S) URL
- Default in code: empty
- Example: `http://127.0.0.1:9090`

### `MEDIA_MANAGER_GRAFANA_URL`
- Purpose: External Grafana base URL shown in the Admin observability UI for dashboard deep links.
- Format: HTTP(S) URL
- Default in code: empty
- Example: `http://127.0.0.1:3000`

### `CANONICAL_READ_CACHE_ENABLED`
- Purpose: Enable canonical metadata read TTL cache (optimization-only path).
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false` (disabled)
- Example: `false`

### `CANONICAL_READ_CACHE_TTL_SECONDS`
- Purpose: Set canonical read cache TTL.
- Format: Positive float or integer (invalid/non-positive values fall back)
- Default in code: `30`
- Example: `30`

### `METADATA_UPSERT_BATCH_SIZE`
- Purpose: Planner metadata upsert batching performance knob.
- Format: Integer; clamped to `[1, 50000]`
- Default in code: `1000`
- Example: `1000`

### `MEDIA_MANAGER_ALLOW_PLANNER_MV_READS`
- Purpose: Experimental override that permits planner callers to use MV read path.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false`
- Safety note: disabled by default to prevent correctness-sensitive planner paths from using eventually-consistent MV reads.
- Example: `false`

## Admin Safety Controls

### `MEDIA_MANAGER_ENV`
- Purpose: Environment gate for destructive admin operations.
- Required for `db-reset`: must be `dev` or `test`
- Default in code: empty (forbidden)
- Example: `dev`

### `MEDIA_MANAGER_DB_RESET_CHALLENGE_WORD`
- Purpose: Explicit challenge token required for non-dry-run `db-reset`.
- Default in code: `media-manager`
- Safety note: change this in shared environments to reduce accidental destructive actions.
- Example: `media-manager`

### `MEDIA_MANAGER_DB_RESET_INCLUDE_DYNAMIC`
- Purpose: Include non-protected dynamically discovered tables in reset plan.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: false
- Safety note: can expand destructive truncation scope.
- Example: `false`

### `MEDIA_MANAGER_BENCHMARKS_ENABLED`
- Purpose: Enable admin benchmark queueing and benchmark worker execution.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false`
- Safety note: benchmark execution is additionally blocked unless `MEDIA_MANAGER_ENV` is `dev` or `test`.
- Example: `false`

### `MEDIA_MANAGER_BENCHMARK_MAX_ITEMS`
- Purpose: Upper bound for accepted synthetic benchmark row counts.
- Format: Integer greater than zero
- Default in code: `10000`
- Safety note: protects benchmark runs from unbounded DB load.
- Example: `10000`

### `MEDIA_MANAGER_BENCHMARK_POLL_INTERVAL_SECONDS`
- Purpose: Poll interval for the benchmark worker loop.
- Format: Positive float or integer
- Default in code: `2.0`
- Example: `2.0`

### `MEDIA_MANAGER_BENCHMARK_STALE_AFTER_SECONDS`
- Purpose: Time before a running benchmark is marked failed as abandoned by the worker.
- Format: Positive float or integer
- Default in code: `900`
- Safety note: defines a durable failure boundary for abandoned benchmark runs; it is not an automatic retry interval.
- Example: `900`

### `MEDIA_MANAGER_BENCHMARK_WORKER_MODE`
- Purpose: Control whether the benchmark worker runs continuously or exits after one poll cycle.
- Allowed values: `forever`, `once`
- Default in code: `forever`
- Example: `forever`

## Operator Console UX Flags

### `MEDIA_MANAGER_DIRECTORY_PICKER_ENABLED`
- Purpose: Enable the optional server-backed directory picker used by the Organize Media `Browse` button.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false`
- Local-use note: this browses directories on the API server host, not on the operator's local workstation browser.
- Safety note: the picker remains read-only and only exposes configured allowed roots; keep it disabled outside trusted/local deployments unless roots are tightly constrained.
- Example: `false`

### `MEDIA_MANAGER_DIRECTORY_PICKER_ROOTS`
- Purpose: Comma-separated absolute directory roots that the optional wizard directory picker may browse.
- Format: Comma-separated absolute directory paths.
- Default in code: empty
- Local-use note: these paths must exist on the same machine/container where the API server runs.
- Safety note: only existing directories are exposed; paths outside these roots are rejected.
- Example: `/srv/media/incoming,/srv/media/archive`

### `MEDIA_MANAGER_VIDEO_THUMBNAILS_ENABLED`
- Purpose: Enable optional server-generated poster thumbnails for video items in the Gallery.
- Truthy values: `1`, `true`, `yes`, `on`
- Default in code: `false`
- Local-use note: thumbnails are generated on the same machine/container that runs the API server, not in the browser.
- Dependency note: requires `ffmpeg` to be installed on the API server host; when unavailable the gallery falls back without posters.
- Example: `false`

### `MEDIA_MANAGER_VIDEO_THUMBNAIL_CACHE_DIR`
- Purpose: Override the local cache directory used for generated video poster thumbnails.
- Format: Absolute or user-home-relative directory path.
- Default in code: system temp directory under `media-manager/video-thumbnails`
- Local-use note: cache files are stored on the API server host and are optimization-only, not durable managed media artifacts.
- Safety note: deleting the cache only forces regeneration; it does not affect canonical media state.
- Example: `/tmp/media-manager/video-thumbnails`

## Source of Truth

- Runtime template: repository root `.env.sample`
- This reference plus `.env.sample` should be kept in sync with code-level env reads.
