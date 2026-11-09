"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { pageHref } from "../_lib/paging";
import { ProgressLink as Link } from "./ProgressLink";

export type PaginationLabels = {
    aria_label: string;
    previous: string;
    next: string;
    page: string;
    of_pages: string;
};

// Which page of a long list is shown, and the address of each: `path` with the filters in `query`.
type PagingProps = {
    path: string;
    query: string;
    page: number;
    pages: number;
    labels: PaginationLabels;
};

const BUTTON_CLASSES = "block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 md:min-w-36 text-center border border-blue-600 hover:border-blue-700";

/**
 * A dropdown of every page in its label, "Page [3] of 100"; picking one opens that page. It sits
 * on its own under a list's result count, and again between Previous and Next at the end.
 */
export function PagePicker({ path, query, page, pages, labels, className = "" }: PagingProps & { className?: string }) {
    const router = useRouter();
    // The links show the progress bar themselves; this goes to the page in code, so it shows its own.
    const [pending, startTransition] = useTransition();

    if (pages <= 1) {
        return null;
    }

    return (
        <label className={`flex items-center gap-2 whitespace-nowrap ${className}`}>
            {labels.page}
            <select
                // Keyed by the page, so after Back or a link it shows the page the address is on.
                key={page}
                // Not in a form, but browsers flag a field with neither a name nor an id.
                name="p"
                defaultValue={page}
                onChange={(event) => {
                    const chosen = Number(event.target.value);
                    startTransition(() => router.push(pageHref(path, query, chosen)));
                }}
                className="p-2 border border-gray-300 rounded-sm cursor-pointer outline-gray-400"
            >
                {Array.from({ length: pages }, (_, index) => (
                    <option key={index} value={index + 1}>{index + 1}</option>
                ))}
            </select>
            {labels.of_pages.replace("{pages}", String(pages))}
            {pending && <span aria-hidden="true" className="link-progress" />}
        </label>
    );
}

/**
 * At the end of a long list: Previous, the page dropdown, and Next. Each page has an address of
 * its own, so a reload, Back or a shared link stays on it, and opening one scrolls to where the
 * rows start.
 *
 * On a phone the dropdown takes the first line and the two buttons share the second, half
 * each; from md up the buttons sit either side of the dropdown. Either way they keep their
 * places, so nothing moves when one is missing on the first or the last page.
 */
export function Pagination({ path, query, page, pages, labels }: PagingProps) {
    if (pages <= 1) {
        return null;
    }

    return (
        <nav aria-label={labels.aria_label} className="grid grid-cols-2 md:grid-cols-[1fr_auto_1fr] items-center gap-x-3 gap-y-4 text-sm">
            <div className="col-start-1 row-start-2 md:row-start-1 md:justify-self-end">
                {page > 1 && (
                    <Link href={pageHref(path, query, page - 1)} rel="nofollow" prefetch={false} className={BUTTON_CLASSES}>
                        {labels.previous}
                    </Link>
                )}
            </div>
            <PagePicker
                path={path}
                query={query}
                page={page}
                pages={pages}
                labels={labels}
                className="col-start-1 col-span-2 row-start-1 justify-self-center md:col-start-2 md:col-span-1"
            />
            <div className="col-start-2 row-start-2 md:col-start-3 md:row-start-1 md:justify-self-start">
                {page < pages && (
                    <Link href={pageHref(path, query, page + 1)} rel="nofollow" prefetch={false} className={BUTTON_CLASSES}>
                        {labels.next}
                    </Link>
                )}
            </div>
        </nav>
    );
}
