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
    StreamerActivityChart,
    StreamerDailyActivity,
    StreamerGameChart,
    StreamerGameActivity,
    StreamerGenreChart,
    StreamerGenreActivity,
    StreamerProfileStreamsList,
    TwitchStream,
} from "../../_components";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type StreamerProfilePageContent = {
    title: string;
    stats_title: string;
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
        per_game: StreamerGameActivity[];
        // Absent from profile-cache entries written before the charts were added;
        // those entries drop out on their own within the cache TTL.
        daily?: StreamerDailyActivity[];
        per_genre?: StreamerGenreActivity[];
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
                        <div className="mb-12">
                            <StreamerActivityChart daily={content.stats.daily ?? []} />
                        </div>
                        <div className="mb-12">
                            <StreamerGenreChart genres={content.stats.per_genre ?? []} />
                        </div>
                        <div className="mb-12">
                            <StreamerGameChart games={content.stats.per_game} />
                        </div>
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
