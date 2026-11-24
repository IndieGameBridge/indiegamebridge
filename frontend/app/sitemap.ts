import type { MetadataRoute } from "next";

import { serverFetch } from "./_lib/server-fetch";

// Server-side route handler, so the non-public FRONTEND_URL env is available.
const baseUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

// Rebuilt at most hourly where Next keeps a cache of it (`next start`), so <lastmod>
// follows the hourly cache rebuilds; without this, the route would be built once and keep
// the build's dates. Production has no such cache (open-next.config.ts), so there each
// request builds it afresh: about 2 seconds and 6 API calls.
export const revalidate = 3600;

// What the sitemap reads from a cached page: its real last-refresh time (the
// CachedPage.updated_at the API exposes) and, for Genre Trends and Games, their language
// pages.
type CachedPageContent = {
    updated_at?: string;
    language_pages?: { slug: string }[];
};

// Returns undefined on any failure, so the entries simply omit <lastmod> rather
// than breaking the whole sitemap.
async function pageContent(key: string): Promise<CachedPageContent | undefined> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        // No visitor's address: reading the request's headers would make the route dynamic and
        // drop the hourly rebuild above. These calls all count as the Worker's own address.
        const response = await serverFetch(`${apiBase}/pages/${key}/`, undefined, { visitor: false });
        if (!response.ok) return undefined;
        return await response.json();
    } catch {
        return undefined;
    }
}

function lastModified(content: CachedPageContent | undefined): Date | undefined {
    return content?.updated_at ? new Date(content.updated_at) : undefined;
}

// Every game page; none on any failure, so the rest of the sitemap stands.
async function gamePages(): Promise<{ slug: string }[]> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        const response = await serverFetch(`${apiBase}/games/pages/`, undefined, { visitor: false });
        if (!response.ok) return [];
        return (await response.json()).pages ?? [];
    } catch {
        return [];
    }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    // Only the indexable public routes. Login, opt-out, and contact are marked
    // noindex (see each page's robots metadata), so they're left out.
    const [home, streamers, genreTrends, games, privacy, gameRows] = await Promise.all([
        pageContent("home"),
        pageContent("streamers"),
        pageContent("genre_trends"),
        pageContent("games"),
        pageContent("privacy"),
        gamePages(),
    ]);
    const genreTrendsModified = lastModified(genreTrends);

    return [
        {
            url: baseUrl,
            lastModified: lastModified(home),
            changeFrequency: "daily",
            priority: 1,
        },
        {
            url: `${baseUrl}/streamers`,
            lastModified: lastModified(streamers),
            changeFrequency: "daily",
            priority: 0.8,
        },
        {
            url: `${baseUrl}/genre-trends`,
            lastModified: genreTrendsModified,
            changeFrequency: "daily",
            priority: 0.8,
        },
        // Each language's own Genre Trends page, rebuilt with the overview.
        ...(genreTrends?.language_pages ?? []).map((page) => ({
            url: `${baseUrl}/genre-trends/${page.slug}`,
            lastModified: genreTrendsModified,
            changeFrequency: "daily" as const,
            priority: 0.7,
        })),
        // The games' numbers change every 6 hours, whatever the page's text does, so no
        // <lastmod> from it: it would say the page last changed with its text.
        {
            url: `${baseUrl}/games`,
            changeFrequency: "hourly",
            priority: 0.8,
        },
        ...(games?.language_pages ?? []).map((page) => ({
            url: `${baseUrl}/games/${page.slug}`,
            changeFrequency: "hourly" as const,
            priority: 0.7,
        })),
        // Each game's own page, the most streamed first, the quiet ones included: once made, a page
        // stays. Rebuilt every 6 hours, so no <lastmod> either.
        ...gameRows.map((page) => ({
            url: `${baseUrl}/game/${page.slug}`,
            changeFrequency: "daily" as const,
            priority: 0.6,
        })),
        {
            url: `${baseUrl}/privacy`,
            lastModified: lastModified(privacy),
            changeFrequency: "yearly",
            priority: 0.5,
        },
    ];
}
