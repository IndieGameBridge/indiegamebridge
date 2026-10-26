import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { getCurrentUser } from "../../_lib/auth";
import { formatDate } from "../../_lib/format";
import { serverFetch } from "../../_lib/server-fetch";
import { LabelChip, PageHeader, PageFooter, PageFooterContent } from "../../_components";
import { ListActions, ListActionsLabels } from "./_components/ListActions";
import { ListDetail, ListEntries, ListEntriesLabels } from "./_components/ListEntries";

// Reads auth cookies + live backend data per request, so never prerender at
// build time (the backend isn't reachable then). Render on demand on the Worker.
export const dynamic = "force-dynamic";

type ListPageContent = ListEntriesLabels & {
    info: string;
    info_one: string;
    saved_from: string;
    list_actions: ListActionsLabels;
    footer_content: PageFooterContent;
};

export const metadata: Metadata = {
    title: "List of Streamers — IndieGameBridge",
    robots: { index: false, follow: false },
};

export default async function ListPage({ params }: { params: Promise<{ list_id: string }> }) {
    const { list_id } = await params;

    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent(`/lists/${list_id}`)}`);
    }

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    // The list is the user's own, so forward their auth cookies the way
    // getCurrentUser does; the page content is shared and needs none.
    const cookieHeader = (await cookies()).toString();
    const [contentResp, listResp] = await Promise.all([
        serverFetch(`${apiBase}/pages/list_of_streamers/`),
        serverFetch(`${apiBase}/api/lists/${encodeURIComponent(list_id)}/`, {
            headers: { cookie: cookieHeader },
            cache: "no-store",
        }),
    ]);

    if (!contentResp.ok) {
        throw new Error(`Failed to load list page content (status ${contentResp.status})`);
    }
    // Another user's list answers 404 as well, so this covers both cases.
    if (listResp.status === 404) {
        notFound();
    }
    if (!listResp.ok) {
        throw new Error(`Failed to load list of streamers (status ${listResp.status})`);
    }

    const { info, info_one, saved_from, list_actions, footer_content, ...entriesLabels }: ListPageContent = await contentResp.json();
    const list: ListDetail = await listResp.json();

    return (
        <Fragment>
            <PageHeader
                user={user}
                title={list.title}
                description={list.description}
                info={(list.streamers_count === 1 ? info_one : info)
                    .replace("{count}", list.streamers_count.toLocaleString())
                    .replace("{date}", formatDate(list.created_at))}
            />

            <main className="flex-1">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto py-24">
                        <div className="mb-16 flex flex-row flex-wrap items-start justify-between gap-4 text-sm">
                            <div className="flex flex-col gap-4 min-w-0">
                                {list.labels.length > 0 && (
                                    <div className="flex flex-row flex-wrap gap-1">
                                        {list.labels.map((label) => <LabelChip key={label.id} label={label} />)}
                                    </div>
                                )}
                                {list.search.length > 0 && (
                                    <p>
                                        <span className="text-brand-blue uppercase">{saved_from}: </span>
                                        {list.search.map((filter) => `${filter.label}: ${filter.value}`).join(" · ")}
                                    </p>
                                )}
                            </div>
                            {/* Just the fields it edits, not the entries already sent to ListEntries. */}
                            <ListActions
                                list={{ id: list.id, title: list.title, description: list.description }}
                                labels={list_actions}
                            />
                        </div>

                        <ListEntries list={list} labels={entriesLabels} />
                    </div>
                </section>
            </main>

            <PageFooter content={footer_content} />
        </Fragment>
    );
}
