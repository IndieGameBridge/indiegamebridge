# IndieGameBridge

A discovery platform connecting indie game developers with streamers.

Indie developers struggle to find the right small streamers to pitch their games to, and many streamers are overlooked by the big publishers' creator programs. IndieGameBridge turns public Twitch streaming data into a searchable directory, so both sides can find each other.

## Status

Live in production. A single VPS polls Twitch around the clock in eight languages (English, French, German, Spanish, Portuguese, Japanese, Italian and Chinese) and keeps millions of streamers' activity searchable. The web frontend runs on Cloudflare Workers.

Next up are AI-curated streamer lists, built on the personal lists feature: see [docs/ai-curated-lists.md](docs/ai-curated-lists.md).

## What it offers

- **Streamer search** (signed in; logged-out visitors get a public page about it, with a sample of real results): filter by language, by peak and average viewers, and by streams and hours streamed over the last four weeks, plus up to three game genres that narrow each other. Up to 10,000 results, 50 to a page. Each result shows a strip of the last 28 days, so regular streamers stand out from those who stopped.
- **Streamer profiles:** the last four weeks' numbers, a day-by-day activity chart, and the recent streams with the games played in them.
- **Personal lists:** save a search as a list or build one by hand, add streamers one at a time or a search's whole result set, and keep a private note on each streamer. The dashboard shows the lists as cards.
- **Exports:** any list or set of search results as an Excel, CSV or JSON file, with each streamer's days streamed in the last 28 days and their dates.
- **Genre Trends** (public): Twitch's game genres compared by streams, streamers and hours streamed over the last four weeks, as a market reference for developers. An overview adds up every language, and each language has a page of its own.
- **Games** (public): the games streamed most right now, narrowed by streamer size, genre and release year. Each game opens a chart of the streams live in every hour of the last four weeks, a line per language, so a streamer can see which hours are quiet. An overview adds up every language, and each language has a page of its own.
- **Privacy controls:** a streamer can opt out, which erases what was collected about them and keeps them out of future polls and the archive files. Signed-in users can turn off usage tracking, exclude their own streams or delete their account. Sign-in, search and export records, and contact messages, are deleted after 12 months.

## How it works

The system has two halves: scheduled management commands that **collect and shape** Twitch data, and a Django REST API with a Next.js frontend that **serves** it. The heavy work happens in cron jobs, so web requests only read small, precomputed tables.

### Data pipeline

| Command | Runs | What it does |
|---|---|---|
| `fetch_twitch_streams` | every 20 minutes | Polls Helix `streams` with one thread per language and keeps the streams in a game category. Each poll round is written as one batched upsert, which adds a snapshot (game, viewers, time) to every live stream. Then it finalizes the streams that ended: one with at least two snapshots and 3 viewers is kept as `offline`, the rest are dropped. A run takes about 1–3 minutes. |
| `categorize_games` | hourly | Asks Helix `games` about categories new to the database. Those with an IGDB id become games, the rest (Just Chatting, say) non-games. |
| `enrich_igdb_games` | hourly | Fills games in from IGDB, with genres, summary and link, then updates the genres of the streams that played them. |
| `approve_streams` | hourly | Approves the ended streams that played a game and deletes those that didn't. A stream still waiting on an uncategorized game is left for the next run. |
| `rebuild_search_stats` | every 6 hours | Rebuilds the search table in one pass: one read of the streams table, then only the rows whose numbers changed are written. |
| `rebuild_game_stats` | every 6 hours | Counts the streams live in each hour of the last 4 weeks, per game, language and streamer size, and sorts each list once, for the Games page. |
| `rebuild_genre_stats` | daily | Recomputes the Genre Trends numbers in one pass, before the page is rebuilt. |
| `refresh_distribution` | daily | Recomputes the home page's chart of streamers by peak viewers. |
| `update_cached_pages` | hourly | Pre-renders the pages' payloads. Home and Streamers hold real streamers and games, so the hourly run keeps their numbers fresh and takes an opted-out streamer off them within the hour. |
| `delete_expired_personal_data` | daily | Deletes personal data older than 12 months. |
| `remove_opted_out_from_archive` | weekly | Rewrites the archive files that still hold streamers who opted out. |
| `archive_streams` | monthly | Writes the month that left the retention window to a Parquet file. |
| `delete_archived_streams` | weekly | Deletes the archived months' streams from Postgres. |

### Read models

Search never scans the streams table, which holds tens of millions of rows. A read model, `StreamerSearchStats`, has one row per streamer and language, summing up their last four weeks: peak and average viewers, hours, streams and the genres played. A search is an indexed filter and sort over that table.

- It's rebuilt in one pass every 6 hours. A streamer's streams are spread all through the streams table, so reading it costs about the same for one streamer as for all of them, and one pass beats many smaller ones. Only the rows whose numbers changed are written, and streamers with no recent streams drop out.
- Genre Trends reads `GenreStats`, rebuilt in one pass once a day. A stream's hours are split across the genres it actually played, by snapshot, so non-game time such as Just Chatting doesn't count.
- The Games pages read `GameStats`, rebuilt in one pass every 6 hours: one row per game, language and streamer size group, holding that line's hours and its place in its list. The newest hour decides the order and an older hour only breaks a tie, so a search reads a stored position instead of comparing 4 weeks of hours.
- Streamer sizes are one set of groups by peak viewers (`apps/streams/size_groups.py`), shared by the home page's chart, the streamer search and the Games pages.
- Public page payloads are pre-rendered into `CachedPage` and served as stored. The home page shows a block per feature, each with a small sample of real data, and headline counts read from the search table.
- A streamer's profile is computed on its first view and cached for an hour.

### Stream archive

Postgres keeps the current month and the two full months before it. Each older month is written once to a zstd-compressed Parquet file, and the file's stream count, id range and SHA-256 are recorded in the admin. The month is then deleted from Postgres in short batches, and each batch is checked against the file first, so no stream leaves the database without being in its file. Streamers who opt out are removed from the files within a week.

The files can be queried as they are, with DuckDB for example:

```sql
SELECT language, count(*) FROM 'archive/streams/*.parquet' GROUP BY 1;
```

### Monitoring

Every cron run is recorded: when it ran, how long it took, whether it failed, and what it did, such as the streams written, approved or archived. The fetch's runs also record their Helix requests and their time, per language and per poll round. The Django admin draws all this as graphs, rendered on the server as SVG with no chart library:

- **Fetch runs:** run time against the 15-minute limit, where the time goes, and Helix requests per minute against Twitch's limit of 800, plus what each run collected, for all languages or one of them.
- **Job runs:** a table of every job that flags the overdue ones, plus each job's run times and its counts per day.
- **Busy time:** every job's runs minute by minute over a 3-hour window, for finding free minutes to deploy or to add a cron job in.
- **Exports:** exports per day, and how many repeat an earlier one.

The pipeline's jobs also ping Healthchecks.io when they succeed.

### Frontend

Next.js (App Router) with server-side rendering and Tailwind CSS, deployed to Cloudflare Workers via OpenNext. Its middleware passes `/api/`, `/auth/` and `/accounts/` through to Django, so the auth cookies stay first-party, and renews an expired access token on the way.

The pages are home, Genre Trends, Games, streamer search (`/streamers`) and profiles, the dashboard and its lists, account, sign-in, opt-out, contact and the privacy policy. They come with page metadata, Open Graph tags, `robots` and a `sitemap`. The Genre Trends pages also carry schema.org `Dataset` structured data, and the overview its FAQ.

### Auth and security

- Sign-in is with Twitch, through django-allauth. Sessions are JWTs (SimpleJWT) in HttpOnly cookies, and signing out blacklists the refresh token.
- Search, profiles, lists and exports need a signed-in user. The home page, Genre Trends and Games are public, and so is `/streamers` itself: a logged-out visitor gets a page about the search, with a sample of real results.
- Cookie-authenticated writes are CSRF-protected.
- DRF throttles limit request rates, counted in Redis so every Gunicorn worker shares them:
  - 120 requests a minute per visitor;
  - 30 searches a minute;
  - 60 list changes and 30 exports an hour;
  - 5 contact messages an hour.
- Cloudflare Turnstile guards the contact form.

## Tech stack

- **Backend:** Python, Django 6, Django REST Framework, PostgreSQL, Redis and Gunicorn. PyArrow writes the Parquet archive, XlsxWriter the Excel exports, and HTTPX makes the Twitch and IGDB calls.
- **Auth:** django-allauth (Twitch) and djangorestframework-simplejwt.
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, and OpenNext on Cloudflare Workers.
- **Data sources:** the [Twitch Helix API](https://dev.twitch.tv/docs/api/reference/) and the [IGDB API](https://api-docs.igdb.com/).

## Project layout

```
backend/
  core/              settings, URLs, the admin's chart engine, the Twitch and IGDB clients
  apps/fetch/        the Twitch polling pipeline and its run records
  apps/streams/      streams, streamers and games, the search, Games and Genre Trends read models, the archive
  apps/userlists/    personal lists
  apps/exports/      Excel, CSV and JSON exports
  apps/users/        accounts, sign-in, opt-out and account settings
  apps/pages/        pre-rendered page payloads
  apps/api/          the search, distribution and page endpoints
  apps/jobs/         run records and graphs for the scheduled jobs
  apps/contact/      the contact form
frontend/            the Next.js app
docs/                design notes for planned features
```

## Running it locally

You need Python 3.12 or newer, PostgreSQL and Node.js. Redis is optional locally: without `REDIS_URL`, rate limits are counted in memory.

The backend, from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r backend/requirements/development.txt
cp .env.example .env             # then fill in the database and the Twitch API keys
cd backend
python manage.py migrate
python manage.py runserver
```

The frontend:

```bash
cd frontend
cp .env.example .env.development
npm install
npm run dev
```

To collect data, run the pipeline's commands in the table's order, starting with `python manage.py fetch_twitch_streams`. Run the tests with `python manage.py test`, from `backend/`.

## Deployment

The backend runs on one DigitalOcean droplet: Gunicorn serves the API, and cron runs the jobs above. The frontend is deployed separately to Cloudflare Workers, with `npm run deploy` from `frontend/`, and calls the API on its own subdomain.

## License

[MIT](LICENSE)
