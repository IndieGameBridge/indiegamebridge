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
                <div className="max-w-[1000] mx-auto pt-16 pb-8 text-sm italic">{content.notes.map((one_note, index) => (
                    <div key={`note-${index}`} className="before:content-(--note-marker) ml-4 before:absolute before:-left-4 relative mb-2"
                        style={{ ["--note-marker" as any]: `"${"*".repeat(index + 1)}"` }}
                    >{one_note}</div>
                ))}</div>
                <div className="max-w-[1000] mx-auto pb-16">
                    <StreamerProfileStreamsList streams={content.streams} />
                </div>
            </main>

            <PageFooter content={content.footer_content}></PageFooter>
        </Fragment>
    );
}
