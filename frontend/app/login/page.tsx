import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent, TwitchLoginButton } from "../_components";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
    title: "Log in — IndieGameBridge",
    robots: { index: false, follow: false },
};

export type LoginPageContent = {
    title: string;
    prompt: string;
    twitch_login_btn: string;
    signing_in: string;
    more_options_note: string;
    footer_content: PageFooterContent;
};

function buildTwitchLoginUrl(rawNext: string | undefined): string {
    // Only forward a same-app path through the OAuth dance - never an absolute URL.
    const next = rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/";
    const finalize = `/auth/finalize-login/?next=${encodeURIComponent(next)}`;
    return `/accounts/twitch/login/?process=login&next=${encodeURIComponent(finalize)}`;
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }>; }) {
    const { next } = await searchParams;
    const twitchLoginUrl = buildTwitchLoginUrl(next);

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const [response, user] = await Promise.all([
        serverFetch(`${apiBase}/pages/login/`),
        getCurrentUser(),
    ]);

    if (!response.ok) {
        throw new Error(`Failed to load login page content (status ${response.status})`);
    }

    const content: LoginPageContent = await response.json();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} />

            <main className="flex-1 px-6">
                <div className="max-w-md mx-auto py-24">
                    <p className="text-gray-600 mb-8 text-center">{content.prompt}</p>
                    <div className="text-center">
                        <TwitchLoginButton
                            href={twitchLoginUrl}
                            label={content.twitch_login_btn}
                            pendingLabel={content.signing_in}
                        />
                    </div>
                    <p className="text-xs text-gray-500 mt-8 text-center">{content.more_options_note}</p>
                </div>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
