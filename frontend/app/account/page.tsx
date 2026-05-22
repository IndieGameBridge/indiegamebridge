import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";

type AccountPageContent = {
    title: string;
    body: string;
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
            <PageHeader user={user} />

            <main className="flex-1 px-6">
                <div className="max-w-2xl mx-auto py-16">
                    <h1 className="text-2xl font-bold mb-4">{content.title}</h1>
                    <p className="text-gray-600">{content.body}</p>
                </div>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
