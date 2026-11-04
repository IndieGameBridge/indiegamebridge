import type { Metadata } from "next";

import { getCurrentUser } from "../_lib/auth";
import { GamesSearchParams, GamesView, fetchGamesContent, gamesMetadata } from "./_components/GamesView";

// Reads auth cookies (for the header) + live backend data per request, so never
// prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
    return gamesMetadata(await fetchGamesContent(), null);
}

export default async function GamesPage({ searchParams }: { searchParams: Promise<GamesSearchParams> }) {
    const [content, user, params] = await Promise.all([
        fetchGamesContent(),
        getCurrentUser(),
        searchParams,
    ]);

    return <GamesView content={content} page={null} user={user} searchParams={params} />;
}
