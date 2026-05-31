import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";
import { TrackingToggle } from "./_components/TrackingToggle";
import { ExclusionToggle } from "./_components/ExclusionToggle";
import { DeleteAccountButton } from "./_components/DeleteAccountButton";

type AccountPageContent = {
    title: string;
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
            <PageHeader user={user} title={content.title} />

            <main className="flex-1 px-6">
                <div className="max-w-2xl mx-auto py-24">
                    <div className="mb-8 flex items-center justify-between gap-4 border-t border-t-gray-400 pt-8">
                        <span className="text-gray-800">Allow feature-usage tracking for service improvement</span>
                        <TrackingToggle initialValue={user.allow_tracking} />
                    </div>

                    <div className="mb-2 flex items-center justify-between gap-4 border-t border-t-gray-400 pt-8">
                        <span className="text-gray-800">Allow streams tracking for my Twitch ID</span>
                        <ExclusionToggle initialExcluded={user.is_twitch_excluded} />
                    </div>
                    <p className="text-sm text-red-600">
                        Turning this off removes all data tied to your Twitch ID and excludes it from future collection.
                        The removed data cannot be restored, though you can turn tracking back on anytime to re-enable future collection.
                        The public page and search results may still show your data for up to an hour while caches refresh.
                    </p>

                    <div className="mt-12 border-t border-t-red-300 pt-8">
                        <h2 className="text-lg font-semibold text-red-700 mb-2">Danger zone</h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Permanently delete your account and account settings. This cannot be undone.
                            Your Twitch streams data is only removed if you tick the option below.
                        </p>
                        <DeleteAccountButton />
                    </div>
                </div>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
