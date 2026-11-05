import { Fragment } from "react/jsx-runtime";
import { ProgressLink as Link } from "../../_components/ProgressLink";

import {
    PageFooter,
    PageFooterContent,
    PageHeader,
    ResultsListLabels,
    SearchFormData,
    SearchStreamerForm,
    SearchStreamerResultsList,
    StreamerData,
} from "../../_components";
import { StreamersGuide, StreamersGuideCopy } from "./StreamersGuide";

export type PublicPageCopy = StreamersGuideCopy & {
    title: string;
    description: string;
    login_note: string;
    login_btn: string;
    demo_title: string;
};

const LOGIN_HREF = `/login?next=${encodeURIComponent("/streamers")}`;

/**
 * What a logged-out visitor gets at /streamers, and so what search engines read: what the
 * search is for, how to use it, that it needs a login, and a demo of it.
 */
export function PublicStreamers({ copy, search_form, search_results, search_total, results_labels, footer_content }: {
    copy: PublicPageCopy;
    search_form: SearchFormData;
    search_results: StreamerData[];
    search_total: number;
    results_labels: ResultsListLabels;
    footer_content: PageFooterContent;
}) {
    return (
        <Fragment>
            <PageHeader
                user={null}
                title={copy.title}
                description={copy.description}
                info={copy.login_note}
                actions={
                    <Link
                        href={LOGIN_HREF}
                        rel="nofollow"
                        prefetch={false}
                        className="text-sm align-baseline inline-block py-1 px-4 bg-twitch-brand text-white font-medium rounded hover:bg-twitch-brand-dark text-center border border-twitch-brand hover:border-twitch-brand-dark"
                    >
                        {copy.login_btn}
                    </Link>
                }
            />

            <main className="w-full">
                <section className="px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <StreamersGuide copy={copy} />
                    </div>
                </section>

                <section className="border-t border-gray-400 px-6">
                    <div className="max-w-[1000] mx-auto pt-24 pb-24">
                        <h2 className="text-2xl font-bold mb-8">{copy.demo_title}</h2>
                        <SearchStreamerForm search_form={search_form} user={null} />
                        <SearchStreamerResultsList
                            search_results={search_results}
                            user={null}
                            labels={results_labels}
                            total={search_total}
                            more_href={LOGIN_HREF}
                        />
                    </div>
                </section>
            </main>

            <PageFooter content={footer_content} />
        </Fragment>
    );
}
