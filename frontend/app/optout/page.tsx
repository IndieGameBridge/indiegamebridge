import type { Metadata } from "next";
import { Fragment } from "react/jsx-runtime";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent, TwitchLoginButton } from "../_components";
import { OptOutButton } from "./_components/OptOutButton";
import { OptOutSuccess } from "./_components/OptOutSuccess";

export const metadata: Metadata = {
    title: "Opt out — IndieGameBridge",
    robots: { index: false, follow: false },
};

export type OptOutPageContent = {
    title: string;
    prompt_title: string;
    not_logged_in: { prompt_content: string; login_btn: string; verifying: string };
    logged_in: { prompt_content: string; optout_btn: string; optout_btn_pending: string };
    already_optout: string;
    success_optout: string;
    footer_content: PageFooterContent;
};

function buildTwitchOptOutUrl(): string {
    // finalize-login with action=optout performs the opt-out (reads Twitch ID,
    // clears session) instead of minting JWT, then redirects to ?status=done.
    const finalize = `/auth/finalize-login/?action=optout&next=${encodeURIComponent("/optout?status=done")}`;
    return `/accounts/twitch/login/?process=login&next=${encodeURIComponent(finalize)}`;
}

export default async function OptOutPage({ searchParams }: { searchParams: Promise<{ status?: string; new?: string; }>; }) {
    const { status, new: isNewOptOut } = await searchParams;

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const [response, user] = await Promise.all([
        serverFetch(`${apiBase}/pages/optout/`),
        getCurrentUser(),
    ]);

    if (!response.ok) {
        throw new Error(`Failed to load opt-out page content (status ${response.status})`);
    }

    const content: OptOutPageContent = await response.json();
    const twitchLoginUrl = buildTwitchOptOutUrl();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        {status === "done"
                            ? <OptOutSuccess content={content} isNewOptOut={isNewOptOut} />
                            : user
                                ? (user.is_twitch_excluded
                                    ? <p className="text-gray-600 mb-16">{content.already_optout}</p>
                                    : (
                                        <Fragment>
                                            <h2 className="text-2xl font-bold mb-8">{content.prompt_title}</h2>
                                            <p className="text-gray-600 mb-16">{content.logged_in.prompt_content}</p>
                                            <OptOutButton label={content.logged_in.optout_btn} pendingLabel={content.logged_in.optout_btn_pending} />
                                        </Fragment>
                                    )
                                )
                                : (
                                    <Fragment>
                                        <h2 className="text-2xl font-bold mb-8">{content.prompt_title}</h2>
                                        <p className="text-gray-600 mb-16">{content.not_logged_in.prompt_content}</p>
                                        <TwitchLoginButton
                                            href={twitchLoginUrl}
                                            label={content.not_logged_in.login_btn}
                                            pendingLabel={content.not_logged_in.verifying}
                                            variant="danger"
                                        />
                                    </Fragment>
                                )
                        }
                    </div>
                </section>
                
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
