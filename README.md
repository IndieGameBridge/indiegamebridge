# IndieGameBridge

A discovery platform connecting indie game developers with streamers.

Indie devs struggle to find the right small streamers to pitch their games to, and some streamers are systematically overlooked by big publisher creator programs. IndieGameBridge aggregates public streaming data into a filterable directory so both sides can find each other.

## Status

Backend and data pipeline are running in production on a single VPS, continuously polling Twitch and building the searchable dataset (millions of streamers tracked). The public web frontend and search are built and in final preparation for public release.

## How it works

The system has two halves: a set of scheduled commands that **ingest and shape** Twitch data, and a Django REST + Next.js layer that **serves** it. Heavy work is done out of band by cron so web requests stay fast.

### Data ingestion pipeline

- **Step #1 — `fetch_twitch_streams`** (`backend/apps/fetch/management/commands/`)
Called via CRON every 20 minutes (from real tests a poll usually takes 2-12 minutes, depending on Twitch load and the number of live streams).
Polls the `helix/streams` endpoint (one thread per language) and upserts streams with a non-empty `game_id` (streams with empty `game_id` are off-topic and not saved).
After polling, it finalizes stale streams (see `_finalize_offline_streams()`): a stream goes `offline` if it has more than 1 snapshot and at least 3 max viewers in any snapshot (others are dropped as irrelevant). For each stream turning offline it upserts a placeholder `Game` (category `new`) if one doesn't exist yet.

- **Step #2 — `categorize_games`**
Called every 20 minutes, offset 12-15 minutes from step #1 to avoid Helix rate-limit contention and spread VPS load.
Polls `helix/games` for all `new` Games: those with a non-empty `igdb_id` become `isgame`, the rest become `isnongame` (names updated either way). Both are kept so future streams reusing the same `game_id` skip re-categorization.

- **Step #3 — `approve_streams`**
Runs a few minutes after step #2, at a 20-minute interval. No API calls: it promotes `offline` streams to `approved`, removes irrelevant ones, or leaves a stream `offline` if it still references an uncategorized (`new`) game, to revisit later.

- **Step #4 — `enrich_igdb_games`**
Low priority, can run hourly or less. Polls the IGDB API to enrich `isgame` Games (IGDB page URL, description, genres, etc.). This data is secondary; the app handles enriched and not-yet-enriched Games gracefully.

### Search read-model

Search never scans the (large, ever-growing) streams table. Instead, a precomputed read-model table, **`StreamerSearchStats`**, holds one row per `(streamer, language)` summarizing the **last 4 weeks**: peak viewers, average viewers, hours streamed, stream count, and the set of genre IDs played. A search is then just an indexed filter + sort over this small table.

- **`rebuild_search_stats`** recomputes the table in rolling chunks behind a saved cursor, so a scheduled cron covers the whole streamer set roughly daily without spiking the VPS. Stats are intentionally ~a day stale; the live polling cadence is unaffected.
- Dormant streamers (no approved streams in the window) and stale language rows are pruned automatically as their chunk is reprocessed.

### Cached pages and widgets

- Public page payloads are pre-rendered into a **`CachedPage`** table by **`update_cached_pages`** and served as-is. The home page (rebuilt daily) embeds a live demo search and headline counts (using O(1) approximations rather than full-table counts).
- The home "Streamer Peak-Viewer Distribution" widget is a separate cached payload built by **`refresh_distribution`** (command-driven only, so a page request never triggers the recompute).

### Frontend

Next.js (App Router) with server-side rendering and Tailwind CSS. Public pages — home, privacy policy, contact (Cloudflare Turnstile protected), opt-out, login — plus auth-gated streamer search (`/streamers`) and streamer profiles. Includes SEO essentials (metadata/Open Graph, `robots`, `sitemap`).

### Auth

Twitch OAuth via django-allauth, with JWT sessions (SimpleJWT). The home page is public; streamer search and profile pages are gated behind login. Opt-out lets a streamer remove their data.

## Tech stack

- **Backend:** Python, Django 6 + Django REST Framework, PostgreSQL, Redis (rate-limit/throttle counters), Gunicorn
- **Auth:** django-allauth (Twitch social login) + djangorestframework-simplejwt
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4, TypeScript
- **Data sources:** Twitch Helix API (https://dev.twitch.tv/docs/api/reference/), IGDB API (https://api-docs.igdb.com/); additional platforms under consideration

## Operations

Runs on a single DigitalOcean droplet. All ingestion and cache-rebuild steps are cron-driven management commands, staggered across the hour and monitored via Healthchecks.io pings. The serving layer is Gunicorn (Django API) plus the Next.js app.

## License

[MIT](LICENSE)
