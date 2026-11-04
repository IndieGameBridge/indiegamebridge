import Link from "next/link";

export type LanguageLink = { slug: string; label: string };

/**
 * Links to an overview page and to each language's page under it, the current one marked.
 * Plain links rather than a toggle, so search engines follow them to every language's page.
 * `query` keeps the filters of a page that has them.
 */
export function LanguageSwitch({ base, pages, current, query = "" }: {
    base: string;
    pages: LanguageLink[];
    current: string | null;
    query?: string;
}) {
    const suffix = query ? `?${query}` : "";
    const items = [
        { key: "all", href: `${base}${suffix}`, label: "All languages", active: current === null },
        ...pages.map((page) => ({
            key: page.slug,
            href: `${base}/${page.slug}${suffix}`,
            label: page.label,
            active: current === page.slug,
        })),
    ];
    return (
        <nav aria-label="Broadcast language" className="flex flex-row flex-wrap gap-2 mb-16 text-sm">
            {items.map((item) => item.active ? (
                <span
                    key={item.key}
                    aria-current="page"
                    className="py-1 px-3 rounded border border-brand-blue bg-brand-blue text-white"
                >
                    {item.label}
                </span>
            ) : (
                // scroll={false}: switching keeps the reader where the charts are.
                <Link
                    key={item.key}
                    href={item.href}
                    scroll={false}
                    className="py-1 px-3 rounded border border-gray-300 hover:border-brand-blue"
                >
                    {item.label}
                </Link>
            ))}
        </nav>
    );
}
