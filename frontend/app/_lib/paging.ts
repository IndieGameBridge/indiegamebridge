// What the API sends with one page of a long list: the page it is, after the API has kept
// it in range, how many pages there are, and how many rows a page holds, which numbers them.
export type Paging = {
    page: number;
    pages: number;
    page_size: number;
};

// Where a page's rows start. A page link scrolls there, past the form above them.
export const RESULTS_ANCHOR = "results";

/** The page an address asks for, sent on as it is: the API keeps it in range. */
export function pageParam(value: string | string[] | undefined): string | undefined {
    return Array.isArray(value) ? value[0] : value;
}

/** One page's address: `path` with its filters in `query`, the page unless it's the first, and the rows' anchor. */
export function pageHref(path: string, query: string, page: number): string {
    const params = new URLSearchParams(query);
    params.delete("p");
    if (page > 1) params.set("p", String(page));
    const search = params.toString();
    return `${path}${search ? `?${search}` : ""}#${RESULTS_ANCHOR}`;
}
