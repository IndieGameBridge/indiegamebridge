import type { Metadata } from "next";

import { getCurrentUser } from "../_lib/auth";
import { GenreTrendsView, fetchGenreTrendsContent, genreTrendsMetadata } from "./_components/GenreTrendsView";

// Reads auth cookies (for the header) + live backend data per request, so never
// prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
    return genreTrendsMetadata(await fetchGenreTrendsContent(), null);
}

export default async function GenreTrendsPage() {
    const [content, user] = await Promise.all([
        fetchGenreTrendsContent(),
        getCurrentUser(),
    ]);

    return <GenreTrendsView content={content} page={null} user={user} />;
}
