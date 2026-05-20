import { Fragment } from "react/jsx-runtime";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import {
    SearchStreamerForm,
    SearchStreamerResultsList,
    SearchFormData,
    StreamerData,
    PageHeader,
    PageFooter,
    PageFooterContent,
} from "../_components";
import { getCurrentUser } from "../_lib/auth";

type StreamersPageContent = {
    title: string;
    description: string;
    info: string;
    search_form: SearchFormData;
    search_results_title: string;
    search_results: StreamerData[];
    footer_content: PageFooterContent;
};

export const metadata: Metadata = {
    title: "Search Streamers — IndieGameBridge",
    robots: { index: false, follow: false },
};

export default async function StreamersPage() {
    const user = await getCurrentUser();
    if (!user) {
        redirect(`/login?next=${encodeURIComponent("/streamers")}`);
    }

    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await fetch(`${apiBase}/pages/home/`);

    if (!response.ok) {
        throw new Error(`Failed to load streamers page content (status ${response.status})`);
    }

    const content: StreamersPageContent = await response.json();

    return (
        <Fragment>
            <PageHeader
                user={user}
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-16 pb-16">
                        <SearchStreamerForm search_form={content.search_form} user={user} />
                        <SearchStreamerResultsList
                            search_results={content.search_results}
                            search_results_title={content.search_results_title}
                        />
                    </div>
                </section>
            </main>

            <PageFooter content={content.footer_content} />
        </Fragment>
    );
}
