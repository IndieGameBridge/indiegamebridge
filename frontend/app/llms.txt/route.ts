import { serverFetch } from "../_lib/server-fetch";

// Server-side route handler, so the non-public FRONTEND_URL env is available.
const baseUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

// Rebuilt at most hourly where Next keeps a cache of it, like the sitemap, so the pages it
// lists follow the cached pages. Production has no such cache (open-next.config.ts), so
// there each request builds it afresh.
export const revalidate = 3600;

type PageCopy = {
    title?: string;
    description?: string;
    seo_description?: string;
};

type CachedPageContent = PageCopy & {
    language_pages?: (PageCopy & { slug: string })[];
    public_page?: PageCopy;
};

// Undefined on any failure, so a line falls back to its plain text rather than the file failing.
async function pageContent(key: string): Promise<CachedPageContent | undefined> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        // No visitor's address: reading the request's headers would make the route dynamic and
        // drop the hourly rebuild above.
        const response = await serverFetch(`${apiBase}/pages/${key}/`, undefined, { visitor: false });
        if (!response.ok) return undefined;
        return await response.json();
    } catch {
        return undefined;
    }
}

// How many of the most streamed game pages the file names.
const GAME_PAGES_LISTED = 20;

// Every game page, the most streamed first; none on any failure.
async function gamePages(): Promise<{ slug: string; name: string }[]> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        const response = await serverFetch(`${apiBase}/games/pages/`, undefined, { visitor: false });
        if (!response.ok) return [];
        return (await response.json()).pages ?? [];
    } catch {
        return [];
    }
}

function link(path: string, title: string, text?: string): string {
    return `- [${title}](${baseUrl}${path})${text ? `: ${text}` : ""}`;
}

function languageLinks(heading: string, base: string, content: CachedPageContent | undefined): string[] {
    const pages = content?.language_pages ?? [];
    if (pages.length === 0) return [];
    return [
        "",
        `### ${heading}`,
        "",
        ...pages.map((page) => link(`${base}/${page.slug}`, page.title ?? page.slug, page.description)),
    ];
}

/**
 * A plain-text guide for AI assistants and agents (the llms.txt convention): what the site is,
 * what each public page shows and where, and what needs a login. Links and descriptions, no data.
 */
export async function GET() {
    const [home, streamers, games, genreTrends, gameRows] = await Promise.all([
        pageContent("home"),
        pageContent("streamers"),
        pageContent("games"),
        pageContent("genre_trends"),
        gamePages(),
    ]);
    const gameLines = gameRows.length === 0 ? [] : [
        "",
        "### Game pages",
        "",
        "A game gets a page at /game/<name> once 10 different streamers played it within 4 weeks, and keeps it: who"
            + " streamed it in the last 4 weeks, in which languages and sizes, at which hours, and which other games"
            + " they also played. The Games pages link to them. The most streamed:",
        "",
        ...gameRows.slice(0, GAME_PAGES_LISTED).map((page) => link(`/game/${page.slug}`, `${page.name} on Twitch`)),
    ];

    const lines = [
        "# IndieGameBridge",
        "",
        `> ${home?.seo_description ?? "Find Twitch streamers who play your indie game's genres."}`,
        "",
        "IndieGameBridge is a free tool for indie game developers. It collects public Twitch streams and shows"
            + " which streamers play which games and genres, in which language, and how many viewers they get.",
        "",
        "## Pages",
        "",
        link("/", home?.title ?? "Home", home?.description),
        link(
            "/streamers",
            streamers?.public_page?.title ?? "Search Twitch streamers",
            [streamers?.seo_description, "The search itself needs a free login with Twitch; this page explains it"
                + " and shows a sample."].filter(Boolean).join(" "),
        ),
        link("/games", games?.title ?? "Games", games?.seo_description),
        link("/genre-trends", genreTrends?.title ?? "Genre trends", genreTrends?.seo_description),
        link("/privacy", "Privacy policy"),
        ...languageLinks("Games in each language", "/games", games),
        ...gameLines,
        ...languageLinks("Genre trends in each language", "/genre-trends", genreTrends),
        "",
        "## Notes",
        "",
        "- The numbers come from public Twitch streams, read through Twitch's API every 20 minutes, with game"
            + " details from IGDB. They cover the last 4 weeks.",
        "- Streamer profiles, the full search, lists and exports need a free login with Twitch.",
        "- There's no public API. The numbers are for reading on these pages: they come from Twitch's API and"
            + " IGDB, so IndieGameBridge can't license them for reuse, and no license is given.",
        "",
    ];

    return new Response(lines.join("\n"), {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
}
