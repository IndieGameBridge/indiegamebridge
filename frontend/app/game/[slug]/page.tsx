import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import { GamePageView, fetchGamePage, gamePageMetadata } from "../_components/GamePageView";

// Reads auth cookies (for the header and the streamers' links) + live backend data per request,
// so never prerender at build time. Render on demand on the Worker.
export const dynamic = "force-dynamic";

type Props = {
    params: Promise<{ slug: string }>;
};

// A game's page by its address, e.g. /game/hollow-knight-silksong. A page once made always
// answers; only an address never given out is a 404.
export async function generateMetadata({ params }: Props): Promise<Metadata> {
    const { slug } = await params;
    const content = await fetchGamePage(slug);
    if (!content) {
        notFound();
    }
    return gamePageMetadata(content);
}

export default async function GamePage({ params }: Props) {
    const [{ slug }, user] = await Promise.all([params, getCurrentUser()]);
    const content = await fetchGamePage(slug);
    if (!content) {
        notFound();
    }
    return <GamePageView content={content} user={user} />;
}
