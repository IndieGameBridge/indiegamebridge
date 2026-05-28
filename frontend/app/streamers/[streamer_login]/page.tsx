import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import { serverFetch } from "../../_lib/server-fetch";
import {
    PageHeader,
    PageFooter,
    PageFooterContent,
    StreamerProfileStreamsList,
    TwitchStream,
} from "../../_components";

type StreamerProfilePageContent = {
    title: string;
    notes: string[];
    streams: TwitchStream[];
    footer_content: PageFooterContent;
    stats: StreamerStats;
};

type StreamerStatsSection = {
    games: {
        name: string;
        genres: string[];
    }[];
    max_viewers: {
        at: string;
        game: string;
        value: number;
    };
    total_streams: number;
    total_time: string;
};

type StreamerStats = {
    all_time: StreamerStatsSection,
    last_4_weeks: StreamerStatsSection,
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

    return (
        <Fragment>
            <PageHeader
                user={user}
                title={content.title}
            />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto mb-24 pt-24">
                        <div className="text-2xl font-bold mb-4">Games in the Last 4 Weeks</div>
                        <div className="mb-8">
                            {content.stats.last_4_weeks.games.map((game, index) => (
                                <div key={`game-${index}`}>
                                    <div className="mb-4">
                                        <div className="text-brand-blue font-bold">{game.name}</div>
                                        <div>{game.genres.join(', ')}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="border-t border-t-gray-400 pb-4 pt-8"><span>Total Streams: </span><span>{content.stats.last_4_weeks.total_streams}</span></div>
                        <div><span>Total Time: </span><span>{content.stats.last_4_weeks.total_time}</span></div>
                    </div>
                    <div className="max-w-[1000] mx-auto mb-24">
                        <div className="text-2xl font-bold mb-4">All Games Played</div>
                        <div className="mb-8">
                            {content.stats.all_time.games.map((game, index) => (
                                <div key={`game-${index}`}>
                                    <div className="mb-4">
                                        <div className="text-brand-blue font-bold">{game.name}</div>
                                        <div>{game.genres.join(', ')}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="border-t border-t-gray-400 pb-4 pt-8"><span>Total Streams: </span><span>{content.stats.all_time.total_streams}</span></div>
                        <div><span>Total Time: </span><span>{content.stats.all_time.total_time}</span></div>
                    </div>
                </section>

                <div className="max-w-[1000] mx-auto mb-24">
                    <div className="text-2xl font-bold mb-4">Streams</div>
                    <StreamerProfileStreamsList streams={content.streams} />
                </div>

                <div className="max-w-[1000] mx-auto pb-24 italic">{content.notes.map((one_note, index) => (
                    <div key={`note-${index}`} className="before:content-(--note-marker) ml-4 before:absolute before:-left-4 relative mb-4"
                        style={{ ["--note-marker" as any]: `"${"*".repeat(index + 1)}"` }}
                    >{one_note}</div>
                ))}</div>
            </main>

            <PageFooter content={content.footer_content}></PageFooter>
        </Fragment>
    );
}
