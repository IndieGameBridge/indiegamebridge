import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type DashboardPageContent = {
    title: string;
    description: string;
    placeholder: string;
    footer_content: PageFooterContent;
};

export const metadata: Metadata = {
    title: "Dashboard — IndieGameBridge",
    robots: { index: false, follow: false },
};

export default async function DashboardPage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent("/dashboard")}`);
    }

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/pages/dashboard/`);

    if (!response.ok) {
        throw new Error(`Failed to load dashboard page content (status ${response.status})`);
    }

    const content: DashboardPageContent = await response.json();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} description={content.description} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <p>{content.placeholder}</p>
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
