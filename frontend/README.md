# IndieGameBridge frontend

The Next.js app of [IndieGameBridge](../README.md). Its pages are rendered on the server, and it runs on Cloudflare Workers through OpenNext.

## Running it locally

```bash
cp .env.example .env.development   # the API's address, this app's address, the Turnstile site key
npm install
npm run dev
```

It needs the Django API running too (see the main README), by default on `http://localhost:8000`.

## Building and deploying

- `npm run build` makes a production build.
- `npm run preview` builds the Worker and runs it locally.
- `npm run deploy` builds the Worker and deploys it to Cloudflare.

## Good to know

- Local settings go in `.env.development`, not `.env`. Next loads `.env` for the production build too, and OpenNext would bundle its local addresses into the Worker. Production takes its values from `wrangler.jsonc`.
- The build uses webpack (`next build --webpack`), since OpenNext can't load Turbopack's chunks.
- Every page is `force-dynamic`: each one fetches the API per request, so none can be prerendered at build time.
- `middleware.ts` keeps Next's `middleware` convention rather than Next 16's `proxy`, because OpenNext runs only edge middleware. It passes `/api/`, `/auth/` and `/accounts/` through to Django as a transparent proxy, so the Twitch sign-in's redirects and cookies reach the browser unchanged. It also renews an expired access token on the way.
- Next merges metadata shallowly, so a page that sets its own `openGraph` or `twitter` replaces the layout's whole object, preview picture included. Such pages spread in `SHARED_OPEN_GRAPH` and `SHARED_TWITTER` from `app/_lib/share-metadata.ts`, which point at `public/og-image.png`.
- `app/llms.txt/route.ts` writes the plain-text guide for AI assistants from the cached pages' titles and descriptions and the most streamed game pages. It and `app/sitemap.ts` ask to be rebuilt at most hourly, but OpenNext has no ISR cache wired (`open-next.config.ts`), so in production each request builds them afresh.
- `app/game/[slug]` is a game's own page. An address the API never gave out is a 404; every page once made stays indexable and in the sitemap, whatever its numbers. Its streamers' links open `/streamers` with a `game` parameter, which the search form keeps when its other filters change. Its month by month section (`GameHistory.tsx`) draws what the API writes: the text, the bars and the tables, whose frames scroll sideways on a phone. A dash marks a number hidden below 5 streamers, and says so on hover and to screen readers.
- Server-rendered pages call the API through `app/_lib/server-fetch.ts`. It and the middleware both send the visitor's address along (`app/_lib/visitor-address.ts`), so the API's rate limits count each visitor.
