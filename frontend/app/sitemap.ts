import type { MetadataRoute } from "next";

import { serverFetch } from "./_lib/server-fetch";

// Server-side route handler, so the non-public FRONTEND_URL env is available.
const baseUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

// Regenerate hourly so <lastmod> tracks the hourly cache rebuilds. Without this
// the route handler is cached indefinitely and lastModified would freeze at the
// build time.
export const revalidate = 3600;

// What the sitemap reads from a cached page: its real last-refresh time (the
// CachedPage.updated_at the API exposes) and, for Genre Trends, its language pages.
type CachedPageContent = {
    updated_at?: string;
    language_pages?: { slug: string }[];
};

// Returns undefined on any failure, so the entries simply omit <lastmod> rather
// than breaking the whole sitemap.
async function pageContent(key: string): Promise<CachedPageContent | undefined> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        const response = await serverFetch(`${apiBase}/pages/${key}/`);
        if (!response.ok) return undefined;
        return await response.json();
    } catch {
        return undefined;
    }
}

function lastModified(content: CachedPageContent | undefined): Date | undefined {
    return content?.updated_at ? new Date(content.updated_at) : undefined;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    // Only the indexable public routes. Login, opt-out, and contact are marked
    // noindex (see each page's robots metadata), so they're left out.
    const [home, genreTrends, privacy] = await Promise.all([
        pageContent("home"),
        pageContent("genre_trends"),
        pageContent("privacy"),
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
        {
            url: `${baseUrl}/privacy`,
            lastModified: lastModified(privacy),
            changeFrequency: "yearly",
            priority: 0.5,
        },
    ];
}
