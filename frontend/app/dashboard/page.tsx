import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getCurrentUser } from "../_lib/auth";
import { serverFetch } from "../_lib/server-fetch";
import { PageHeader, PageFooter, PageFooterContent } from "../_components";
import { ListCard, ListCardData } from "./_components/ListCard";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type DashboardPageContent = {
    title: string;
    description: string;
    empty_state: string;
    empty_state_cta: string;
    footer_content: PageFooterContent;
};

type ListsResponse = {
    lists: ListCardData[];
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
    // The lists are the user's own, so forward their auth cookies the way
    // getCurrentUser does; the page content is shared and needs none.
    const cookieHeader = (await cookies()).toString();
    const [contentResp, listsResp] = await Promise.all([
        serverFetch(`${apiBase}/pages/dashboard/`),
        serverFetch(`${apiBase}/api/lists/`, { headers: { cookie: cookieHeader }, cache: "no-store" }),
    ]);

    if (!contentResp.ok) {
        throw new Error(`Failed to load dashboard page content (status ${contentResp.status})`);
    }
    if (!listsResp.ok) {
        throw new Error(`Failed to load lists of streamers (status ${listsResp.status})`);
    }

    const content: DashboardPageContent = await contentResp.json();
    const { lists }: ListsResponse = await listsResp.json();

    return (
        <Fragment>
            <PageHeader user={user} title={content.title} description={content.description} />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        {lists.length > 0 ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {lists.map((list) => <ListCard key={list.id} list={list} />)}
                            </div>
                        ) : (
                            <div className="border-t border-t-gray-400 pt-8">
                                <p className="mb-8 text-gray-800">{content.empty_state}</p>
                                <Link href="/streamers" className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700">
                                    {content.empty_state_cta}
                                </Link>
                            </div>
                        )}
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
