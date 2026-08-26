import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import { serverFetch } from "../../_lib/server-fetch";
import { formatStreamTime } from "../../_lib/format";
import {
    PageHeader,
    PageFooter,
    PageFooterContent,
    StreamerProfileStreamsList,
    TwitchStream,
} from "../../_components";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type StreamerProfilePageContent = {
    title: string;
    stats_title: string;
    games_title: string;
    no_games: string;
    streams_title: string;
    show_more: string;
    notes: string[];
    streams: TwitchStream[];
    footer_content: PageFooterContent;
    stats: {
        recent: {
            streams: number;
            duration: string;
            maxv: {
                val: number;
                at: string;
                game: string;
            } | null;
        };
        per_game: {
            name: string;
            genres: string[];
            duration: string;
            streams: number;
            maxv: number;
            avgv: number;
        }[];
    };
};

export const metadata: Metadata = {
    robots: { index: false, follow: false },
};

export default async function StreamerProfilePage({ params }: { params: Promise<{ streamer_login: string }>; }) {
    const { streamer_login } = await params;

    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent(`/streamers/${streamer_login}`)}`);
    }

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/streamer_profile/?twitch_login=${encodeURIComponent(streamer_login)}`);

    if (!response.ok) {
        throw new Error(`Failed to load streamer profile page content (status ${response.status})`);
    }

    const content: StreamerProfilePageContent = await response.json();

    const twitchUrl = "https://www.twitch.tv/";

    return (
        <Fragment>
            <PageHeader
                user={user}
                title={content.title}
                link_to_twitch={twitchUrl + streamer_login}
            />

            <main className="flex-1">

                {/* Last 4-Week Stats */}
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto mb-24 pt-24">
                        <div className="text-2xl font-bold mb-8">{content.stats_title}</div>
                        <div>
                            <div className="mb-1"><span className="text-brand-blue">Number of streams: </span><span>{content.stats.recent.streams}</span></div>
                            <div className="mb-1"><span className="text-brand-blue">Total time: </span><span>{content.stats.recent.duration}</span></div>
                            {content.stats.recent.maxv && (
                                <Fragment>
                                    <div className="text-brand-blue mb-2">Peak: </div>
                                    <div className="ml-4">
                                        <div className="mb-1">• {content.stats.recent.maxv.val} viewers</div>
                                        <div className="mb-1">• {content.stats.recent.maxv.game}</div>
                                        <div>• {formatStreamTime(content.stats.recent.maxv.at)} UTC</div>
                                    </div>
                                </Fragment>
                            )}
                        </div>
                    </div>
                </section>

                {/* Last 4-Week Games */}
                <section className="px-6 border-t border-t-gray-400">
                    <div className="max-w-[1000] mx-auto mb-24 pt-24">
                        <div className="text-2xl font-bold mb-8">{content.games_title}</div>
                        {content.stats.per_game.length === 0 ? (
                            <div className="italic">{content.no_games}</div>
                        ) : (content.stats.per_game.map((game, index) => (
                                <div key={`game-${index}`} className="mb-24">
                                    <div className="font-bold mb-2">{game.name}</div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 mb-4 border-t border-t-gray-400 pt-4 text-sm gap-4">
                                        <div className="col-span-1 md:col-span-1 lg:col-span-2 grid grid-cols-1 md:grid-cols-1 lg:grid-cols-2 gap-4">
                                            <div className="text-nowrap">Peak {game.maxv}</div>
                                            <div className="text-nowrap">Avg {game.avgv}</div>
                                        </div>
                                        <div className="text-nowrap">{game.streams} streams • {game.duration}</div>
                                    </div>
                                    <div className="mb-4 flex flex-row items-center text-sm">
                                        <div className="flex flex-row flex-wrap gap-2">
                                            {game.genres.map((genre, index) => (
                                                <div key={`genre-${index}`} className="py-1 px-2 bg-gray-200 rounded-sm">{genre}</div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </section>

                {/* Streams */}
                <section className="px-6 border-t border-t-gray-400">
                    <div className="max-w-[1000] mx-auto mb-24 pt-24">
                        <div className="text-2xl font-bold mb-8">{content.streams_title}</div>
                        <StreamerProfileStreamsList streams={content.streams} showMoreLabel={content.show_more} />
                    </div>
                    <div className="max-w-[1000] mx-auto pb-24 italic">{content.notes.map((one_note, index) => (
                        <div key={`note-${index}`} className="before:content-(--note-marker) ml-4 before:absolute before:-left-4 relative mb-4 pt-2"
                            style={{ "--note-marker": `"${"*".repeat(index + 1)}"` } as React.CSSProperties}
                        >{one_note}</div>
                    ))}</div>
                </section>
            </main>

            <PageFooter content={content.footer_content}></PageFooter>
        </Fragment>
    );
}
