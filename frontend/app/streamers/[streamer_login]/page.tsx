import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import { serverFetch } from "../../_lib/server-fetch";
import { formatStreamTime } from "../../_lib/format";
import { PageHeader, PageFooter, PageFooterContent, StreamSnapshotsChart } from "../../_components";

type Snapshot = {
    g: number;
    t: number;
    v: number;
};

type TwitchStream = {
    id: number;
    games: string[];
    host_game_ids: number[];
    duration: string;
    language: string;
    snapshots: Snapshot[];
    started_at: string;
    finished_at: string;
    max_viewers: number;
};

type StreamerProfilePageContent = {
    title: string;
    body: string;
    streams: TwitchStream[];
    footer_content: PageFooterContent;
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

            <main className="flex-1 px-6">
                <div className="max-w-[1000] mx-auto pb-16">
                    {content.streams.map((stream, index) => (
                        <div key={`stream-${stream.id}`}
                            className="border border-gray-300 mt-6 p-6 rounded-sm bg-white text-sm"
                        >
                            <StreamSnapshotsChart
                                snapshots={stream.snapshots}
                                started_at={stream.started_at}
                                games={stream.games}
                                host_game_ids={stream.host_game_ids}
                            />
                            <div><span className="text-brand-blue">Started: </span><span>{formatStreamTime(stream.started_at)}</span></div>
                            <div><span className="text-brand-blue">Finished: </span><span>{formatStreamTime(stream.finished_at)}</span></div>
                            <div><span className="text-brand-blue">Duration: </span><span>{stream.duration}</span></div>
                            <div><span className="text-brand-blue">Peak Viewers: </span><span>{stream.max_viewers}</span></div>
                            <div><span className="text-brand-blue">Language: </span><span>{stream.language}</span></div>
                        </div>
                    ))}
                </div>
            </main>

            <PageFooter content={content.footer_content}></PageFooter>
        </Fragment>
    );
}
