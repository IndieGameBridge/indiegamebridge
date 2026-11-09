"use client";

import { Fragment } from "react";
import { ProgressLink as Link } from "./ProgressLink";

import { CurrentUser } from "../_lib/auth";
import type { Paging } from "../_lib/paging";
import { AddToList, AddToListLabels } from "./AddToList";
import { PagePicker, Pagination, PaginationLabels } from "./Pagination";
import { StreamerStats } from "./StreamerStats";

export type StreamerData = {
    profile_id: number;
    login: string;
    display_name: string;
    streams_count: number;
    hours_streamed: number;
    peak_viewers: number;
    avg_viewers: number;
    genres: string[];
};

export type ResultsListLabels = {
    found_count?: string;
    found_count_one?: string;
    view_profile: string;
    login_to_view_profile: string;
    // The public demo's link to the login page.
    show_more: string;
    pagination: PaginationLabels;
};

const PROFILE_LINK_CLASSES = "text-sm align-baseline inline-block p-1 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 text-center border border-blue-600 hover:border-blue-700";

type Props = {
    search_results: StreamerData[];
    user: CurrentUser | null;
    labels: ResultsListLabels;
    total?: number;
    // The page of a real search's results, with the search's filters for the other pages'
    // addresses. The public demo shows its few rows with none.
    paging?: Paging & { query: string };
    more_href?: string;
    // Shown beside the result count, e.g. the streamers page's "Save to list".
    count_actions?: React.ReactNode;
    // Puts an "Add to list" menu on every row. Only for signed-in pages: the
    // public page's demo leaves it out.
    add_to_list?: AddToListLabels;
};

export function SearchStreamerResultsList({
    search_results,
    user,
    labels,
    total,
    paging,
    more_href,
    count_actions,
    add_to_list,
}: Props) {
    // Rows are numbered through the whole search, so page 2's first is #51.
    const firstNumber = paging ? (paging.page - 1) * paging.page_size + 1 : 1;

    return (
        <div>
            {/* Result count, between the form and the listing.
                Only shown when a real total is supplied (the home demo passes none). */}
            {total !== undefined && labels.found_count && (
                <div className="mb-8 flex flex-row flex-wrap items-start justify-between gap-4">
                    {/* The page dropdown under the count, so another page is a pick away
                        without going down to the end of this one. */}
                    <div className="flex flex-col items-start gap-3">
                        <div className="text-lg text-brand-blue">
                            {total === 1 && labels.found_count_one
                                ? labels.found_count_one
                                : labels.found_count.replace("{count}", total.toLocaleString())}
                        </div>
                        {paging && (
                            <PagePicker
                                path="/streamers"
                                query={paging.query}
                                page={paging.page}
                                pages={paging.pages}
                                labels={labels.pagination}
                                className="text-sm"
                            />
                        )}
                    </div>
                    {/* A Fragment's only child rather than a sibling in this row: an
                        element passed in from a server component can still be loading
                        here, and React then reports it as an unkeyed list item. */}
                    <Fragment>{count_actions}</Fragment>
                </div>
            )}

            {search_results.map((one_result, index) => (
                <div key={one_result.profile_id} className="border-t border-t-gray-400 pt-2 mb-16 bg-white">

                    {/* Listing header */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-center pb-2 gap-6">
                        <div className="font-bold text-lg"><span className="text-gray-500 font-normal mr-1">#{firstNumber + index} </span><span>{one_result.display_name}</span></div>
                        <div className="flex flex-col md:flex-row lg:flex-row justify-end gap-6">
                            {add_to_list && <AddToList profileId={one_result.profile_id} labels={add_to_list} />}
                            {user
                                ? <Link className={PROFILE_LINK_CLASSES} href={`/streamers/${one_result.login}`}
                                    rel="nofollow" target="_blank" title="View streamer profile">{labels.view_profile}</Link>
                                // Profiles need a login, so a logged-out visitor's link says so and goes
                                // to the login page, which brings them back to the profile.
                                : <Link className={PROFILE_LINK_CLASSES}
                                    href={`/login?next=${encodeURIComponent(`/streamers/${one_result.login}`)}`}
                                    rel="nofollow" prefetch={false}>{labels.login_to_view_profile}</Link>
                            }
                        </div>
                    </div>

                    {/* Listing body */}
                    <StreamerStats stats={one_result} />
                </div>
            ))}

            {paging && (
                <Pagination
                    path="/streamers"
                    query={paging.query}
                    page={paging.page}
                    pages={paging.pages}
                    labels={labels.pagination}
                />
            )}

            {/* Demo Show More leads to target URL */}
            {more_href && (
                <div className="text-center">
                    <Link
                        href={more_href}
                        rel="nofollow"
                        prefetch={false}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
                    >
                        {labels.show_more}
                    </Link>
                </div>
            )}
        </div>
    );
};
