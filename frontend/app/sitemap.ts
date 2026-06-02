import type { MetadataRoute } from "next";

import { serverFetch } from "./_lib/server-fetch";

// Server-side route handler, so the non-public FRONTEND_URL env is available.
const baseUrl = process.env.FRONTEND_URL ?? "http://localhost:3000";

// Regenerate hourly so <lastmod> tracks the hourly cache rebuilds. Without this
// the route handler is cached indefinitely and lastModified would freeze at the
// build time.
export const revalidate = 3600;

// Real last-refresh time of a cached page (the CachedPage.updated_at the API
// exposes), used as the sitemap <lastmod>. Returns undefined on any failure so
// the entry simply omits <lastmod> rather than breaking the whole sitemap.
async function pageLastModified(key: string): Promise<Date | undefined> {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    try {
        const response = await serverFetch(`${apiBase}/pages/${key}/`);
        if (!response.ok) return undefined;
        const data = await response.json();
        return data.updated_at ? new Date(data.updated_at) : undefined;
    } catch {
        return undefined;
    }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    // Only the indexable public routes. Login, opt-out, and contact are marked
    // noindex (see each page's robots metadata), so they're left out.
    const [homeModified, privacyModified] = await Promise.all([
        pageLastModified("home"),
        pageLastModified("privacy"),
    ]);

    return [
        {
            url: baseUrl,
            lastModified: homeModified,
            changeFrequency: "hourly",
            priority: 1,
        },
        {
            url: `${baseUrl}/privacy`,
            lastModified: privacyModified,
            changeFrequency: "yearly",
            priority: 0.5,
        },
    ];
}
