import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";
import { TrackingToggle } from "./_components/TrackingToggle";
import { ExclusionToggle } from "./_components/ExclusionToggle";
import { DeleteAccountButton } from "./_components/DeleteAccountButton";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type AccountPageContent = {
    title: string;
    description: string;
    tracking_label: string;
    exclusion_label: string;
    exclusion_warning: string;
    exclusion_confirm: string;
    danger_zone: {
        title: string;
        description: string;
        optout_label: string;
        delete_confirm: string;
        delete_btn: string;
    };
    footer_content: PageFooterContent;
};

export const metadata: Metadata = {
    title: "Account Settings — IndieGameBridge",
    robots: { index: false, follow: false },
};

export default async function AccountPage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent("/account")}`);
    }

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/account/`);

    if (!response.ok) {
        throw new Error(`Failed to load account page content (status ${response.status})`);
    }

    const content: AccountPageContent = await response.json();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} description={content.description} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <div className="mb-8 flex items-center justify-between gap-4 border-t border-t-gray-400 pt-8">
                            <span className="text-gray-800">{content.tracking_label}</span>
                            <TrackingToggle initialValue={user.allow_tracking} />
                        </div>

                        <div className="mb-4 flex items-center justify-between gap-4 border-t border-t-gray-400 pt-8">
                            <span className="text-gray-800">{content.exclusion_label}</span>
                            <ExclusionToggle initialExcluded={user.is_twitch_excluded} confirmText={content.exclusion_confirm} />
                        </div>
                        <p className="text-sm text-red-600">{content.exclusion_warning}</p>

                        <div className="mt-24 border-t border-t-red-300 pt-8">
                            <h2 className="text-lg font-semibold text-red-700 mb-4">{content.danger_zone.title}</h2>
                            <p className="text-sm text-gray-600 mb-8">{content.danger_zone.description}</p>
                            <DeleteAccountButton
                                optOutLabel={content.danger_zone.optout_label}
                                confirmText={content.danger_zone.delete_confirm}
                                buttonLabel={content.danger_zone.delete_btn}
                            />
                        </div>
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
