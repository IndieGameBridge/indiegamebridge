import { cache } from "react";
import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import { PageFooter, PageFooterContent, PageHeader, Standouts, StandoutsContent } from "../../_components";
import { ProgressLink as Link } from "../../_components/ProgressLink";
import type { CurrentUser } from "../../_lib/auth";
import { serverFetch } from "../../_lib/server-fetch";
import { SHARED_OPEN_GRAPH, SHARED_TWITTER } from "../../_lib/share-metadata";
import { HourBars, HourBarsContent, ShareBars, ShareBarsContent, StatTile, StatTiles } from "./GameCharts";
import { GameHistory, GameHistoryContent } from "./GameHistory";

type AlsoPlayed = {
    title: string;
    caption: string;
    games: { name: string; href: string; detail: string }[];
};

type StreamersCta = {
    title: string;
    text: string;
    login_text: string;
    login_href: string;
    search_text: string;
    // The search for the game's streamers, one language at a time.
    search_links: { label: string; streamers: string; href: string }[];
};

// A game's page, as /games/pages/<slug>/ serves it. Below 5 streamers in the 4 weeks the page
// has totals only, and the sections after the tiles are null; with none, no tiles either.
export type GamePageContent = {
    slug: string;
    name: string;
    title: string;
    description: string;
    info: string | null;
    breadcrumb: { label: string; href: string };
    seo_title: string;
    seo_description: string;
    summary: StandoutsContent;
    tiles: StatTile[];
    sizes: ShareBarsContent | null;
    languages: ShareBarsContent | null;
    hours_of_day: HourBarsContent | null;
    weeks: ShareBarsContent | null;
    // Its past months: null until a month it was streamed in has been counted, and absent from
    // an API older than the month by month section.
    history?: GameHistoryContent | null;
    also_played: AlsoPlayed | null;
    cta: StreamersCta | null;
    notes: { title: string; items: string[] };
    footer_content: PageFooterContent;
};

/**
 * The game's page, or null for an address never given out. Once per request: the metadata and
 * the page share it, so a search engine reading page after page costs the API one call each.
 */
export const fetchGamePage = cache(async (slug: string): Promise<GamePageContent | null> => {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/games/pages/${encodeURIComponent(slug)}/`);
    if (response.status === 404) return null;
    if (!response.ok) {
        throw new Error(`Failed to load game page (status ${response.status})`);
    }
    return await response.json();
});

// Every game page may be indexed, whatever its numbers: once in search results, a page stays there.
export function gamePageMetadata(content: GamePageContent): Metadata {
    const path = `/game/${content.slug}`;
    return {
        title: content.seo_title,
        description: content.seo_description,
        alternates: { canonical: path },
        openGraph: {
            ...SHARED_OPEN_GRAPH,
            title: content.seo_title,
            description: content.seo_description,
            url: path,
        },
        twitter: {
            ...SHARED_TWITTER,
            title: content.seo_title,
            description: content.seo_description,
        },
    };
}

function AlsoPlayedGames({ also }: { also: AlsoPlayed }) {
    return (
        <section>
            <h2 className="text-xl font-bold mb-2">{also.title}</h2>
            <p className="text-sm text-gray-600 mb-5">{also.caption}</p>
            <div className="flex flex-wrap gap-3">
                {also.games.map((game) => (
                    <Link
                        key={game.href}
                        href={game.href}
                        className="inline-block max-w-full px-4 py-2.5 border border-brand-blue rounded-md text-brand-blue hover:bg-gray-100 wrap-anywhere"
                    >
                        {game.name} <span className="text-gray-600">· {game.detail}</span>
                    </Link>
                ))}
            </div>
        </section>
    );
}

/** Its streamers: in the search for a logged-in user, a language at a time; otherwise the way to log in. */
function GameStreamers({ cta, user }: { cta: StreamersCta; user: CurrentUser | null }) {
    return (
        <section className="border border-gray-300 rounded-lg p-6 md:p-8 flex flex-wrap items-center gap-6">
            <div className="flex-1 basis-80 min-w-0">
                <h2 className="text-xl font-bold mb-2">{cta.title}</h2>
                <p className="text-gray-700">{user ? cta.search_text : cta.text}</p>
                {user && (
                    <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
                        {cta.search_links.map((link) => (
                            <li key={link.href}>
                                <Link href={link.href} className="underline text-blue-700 hover:text-blue-500">{link.label}</Link>
                                <span className="text-gray-600"> · {link.streamers}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            {!user && (
                <Link
                    href={cta.login_href}
                    rel="nofollow"
                    prefetch={false}
                    className="inline-block py-2 px-4 bg-twitch-brand text-white font-medium rounded hover:bg-twitch-brand-dark text-center border border-twitch-brand hover:border-twitch-brand-dark"
                >
                    {cta.login_text}
                </Link>
            )}
        </section>
    );
}

/** A game's public page: who streamed it in the last 4 weeks, in which languages and sizes, when,
 * and what else they played. */
export function GamePageView({ content, user }: { content: GamePageContent; user: CurrentUser | null }) {
    return (
        <Fragment>
            <PageHeader
                user={user}
                title={content.title}
                description={content.description}
                info={content.info ?? undefined}
                breadcrumb={
                    <Fragment>
                        <Link href={content.breadcrumb.href} className="text-white underline">{content.breadcrumb.label}</Link>
                        {" › "}{content.name}
                    </Fragment>
                }
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24 flex flex-col gap-16">
                        <Standouts standouts={content.summary} />
                        {content.tiles.length > 0 && <StatTiles tiles={content.tiles} />}
                        {(content.sizes || content.languages) && (
                            <div className="flex flex-wrap gap-x-14 gap-y-16">
                                {content.sizes && <ShareBars content={content.sizes} labelWidth="w-16" className="flex-1 basis-80" />}
                                {content.languages && <ShareBars content={content.languages} labelWidth="w-22" className="flex-1 basis-80" />}
                            </div>
                        )}
                        {content.hours_of_day && <HourBars content={content.hours_of_day} />}
                        {content.weeks && <ShareBars content={content.weeks} labelWidth="w-28" className="max-w-160" />}
                        {content.history && <GameHistory history={content.history} />}
                        {content.also_played && <AlsoPlayedGames also={content.also_played} />}
                        {content.cta && <GameStreamers cta={content.cta} user={user} />}
                        <section className="border-t border-gray-300 pt-8">
                            <h2 className="text-lg font-bold mb-3">{content.notes.title}</h2>
                            <ul className="list-disc pl-5 text-sm text-gray-700 flex flex-col gap-2">
                                {content.notes.items.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                        </section>
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
