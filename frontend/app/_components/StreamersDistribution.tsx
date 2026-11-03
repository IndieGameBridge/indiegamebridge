import { serverFetch } from "../_lib/server-fetch";

type Bucket = { x: string; y: number };

type DistributionLanguage = {
    code: string;
    label: string;
    // Says when a row covers less than 4 weeks, for a language collected since lately.
    note: string | null;
};

type DistributionData = {
    title: string;
    description: string;
    // In page order: the buckets' keys keep none, since JSONB sorts them.
    languages?: DistributionLanguage[];
    buckets: Record<string, Bucket[]>;
};

// One series per row, in the blue the site's other charts give their first series.
const BAR_COLOR = "#0072B2";

export async function StreamersDistribution() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/streamers/distribution/`);

    if (!response.ok) {
        return null;
    }

    const data: DistributionData = await response.json();

    return (
        <section className="px-6">
            <div className="max-w-[1000] mx-auto pt-12 pb-24">
                <h2 className="text-2xl font-bold mb-8">{data.title}</h2>
                <p className="mb-12">{data.description}</p>

                {/* A payload cached before the rows came in has no languages, and shows
                    no chart until refresh_distribution has run again. */}
                <DistributionRows title={data.title} languages={data.languages ?? []} buckets={data.buckets} />
            </div>
        </section>
    );
}


type RowsProps = {
    title: string;
    languages: DistributionLanguage[];
    buckets: Record<string, Bucket[]>;
};

/**
 * Small multiples: a row per language, each a column chart of the share of that
 * language's streamers in each peak-viewer range.
 *
 * Shares rather than counts, since English outnumbers the others roughly ten to one.
 * The rows line up on the same ranges and share one scale, so their shapes compare at
 * a glance. Each row names its total, so equal-looking columns aren't misread as
 * equal audiences.
 */
function DistributionRows({ title, languages, buckets }: RowsProps) {
    // Only languages the payload carries buckets for.
    const rows = languages
        .filter((lang) => buckets[lang.code]?.length)
        .map((lang) => {
            const counts = buckets[lang.code].map((bucket) => bucket.y);
            const total = counts.reduce((sum, count) => sum + count, 0);
            return {
                ...lang,
                counts,
                total,
                shares: counts.map((count) => (total > 0 ? (count / total) * 100 : 0)),
            };
        });
    if (rows.length === 0) return null;

    // Every language uses the same ranges, so the first one defines the columns.
    const ranges = buckets[rows[0].code].map((bucket) => bucket.x);
    const maxShare = Math.max(...rows.flatMap((row) => row.shares), 1);

    // Fixed coordinate system, matching the site's other charts: the SVG keeps a
    // readable pixel size and scrolls horizontally on narrow screens.
    const width = 1000;
    // Left gutter: the language, its total and any note, on three lines.
    const labelWidth = 200;
    const chartLeft = labelWidth;
    const slotWidth = (width - labelWidth) / ranges.length;
    const columnWidth = Math.round(slotWidth * 0.62);
    // The ranges head the columns once, above the first row.
    const headerHeight = 22;
    // Room for the share printed above the tallest column.
    const valueHeight = 16;
    const columnsHeight = 44;
    const rowGap = 16;
    const rowHeight = valueHeight + columnsHeight + rowGap;
    const height = headerHeight + rows.length * rowHeight - rowGap + 2;

    return (
        <div>
            <div className="overflow-x-auto">
            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={title}
            >
                <title>{title}</title>
                <desc>
                    {"Column charts, one row per broadcast language, of the share of each language's"
                        + " streamers whose peak viewer count over the last 4 weeks falls in each range."
                        + " The rows share the ranges and one scale."}
                </desc>

                {/* The ranges, heading the columns. */}
                <text
                    x={labelWidth - 10}
                    y={headerHeight / 2}
                    textAnchor="end"
                    dominantBaseline="central"
                    fontSize="11"
                    className="fill-current selection:fill-white"
                >
                    Peak viewers
                </text>
                {ranges.map((range, k) => (
                    <text
                        key={range}
                        x={chartLeft + k * slotWidth + slotWidth / 2}
                        y={headerHeight / 2}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize="11"
                        className="fill-current selection:fill-white"
                    >
                        {range}
                    </text>
                ))}

                {rows.map((row, i) => {
                    const rowTop = headerHeight + i * rowHeight;
                    const baseline = rowTop + valueHeight + columnsHeight;
                    return (
                        <g key={row.code}>
                            {/* The language, its total and any note, right-aligned against the columns. */}
                            <text
                                x={labelWidth - 10}
                                y={rowTop + 22}
                                textAnchor="end"
                                fontSize="13"
                                fontWeight="600"
                                className="fill-current selection:fill-white"
                            >
                                {row.label}
                            </text>
                            <text
                                x={labelWidth - 10}
                                y={rowTop + 38}
                                textAnchor="end"
                                fontSize="11"
                                className="fill-current selection:fill-white"
                            >
                                {`${row.total.toLocaleString()} ${row.total === 1 ? "streamer" : "streamers"}`}
                            </text>
                            {row.note && (
                                <text
                                    x={labelWidth - 10}
                                    y={rowTop + 52}
                                    textAnchor="end"
                                    fontSize="10"
                                    className="fill-current selection:fill-white"
                                >
                                    {row.note}
                                </text>
                            )}

                            <line x1={chartLeft} x2={width} y1={baseline} y2={baseline} stroke="#e5e7eb" />
                            {row.shares.map((share, k) => {
                                // Any non-zero share gets at least a 1px sliver.
                                const columnHeight = share > 0
                                    ? Math.max(1, (share / maxShare) * columnsHeight)
                                    : 0;
                                const x = chartLeft + k * slotWidth + (slotWidth - columnWidth) / 2;
                                return (
                                    <g key={ranges[k]}>
                                        <rect
                                            x={x}
                                            y={baseline - columnHeight}
                                            width={columnWidth}
                                            height={columnHeight}
                                            fill={BAR_COLOR}
                                        >
                                            <title>
                                                {`${row.label}, ${ranges[k]} peak viewers: ${share.toFixed(1)}%`
                                                    + ` (${row.counts[k].toLocaleString()} streamers)`}
                                            </title>
                                        </rect>
                                        {/* The share, just above the column. */}
                                        <text
                                            x={x + columnWidth / 2}
                                            y={baseline - columnHeight - 4}
                                            textAnchor="middle"
                                            fontSize="10"
                                            className="fill-current selection:fill-white"
                                        >
                                            {`${share.toFixed(1)}%`}
                                        </text>
                                    </g>
                                );
                            })}
                        </g>
                    );
                })}
            </svg>
            </div>

            {/* Screen-reader + SEO-friendly table mirroring the chart. sr-only sits on a
                wrapper, not on the table: a table box can't shrink below its min-content
                width, so sr-only's width:1px is ignored there and the hidden table still
                widens the page. */}
            <div className="sr-only">
            <table>
                <caption>{title}</caption>
                <thead>
                    <tr>
                        <th>Language</th>
                        {ranges.map((range) => (
                            <th key={range}>{`${range} peak viewers`}</th>
                        ))}
                        <th>Streamers</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <tr key={row.code}>
                            <td>{row.note ? `${row.label} (${row.note})` : row.label}</td>
                            {row.shares.map((share, k) => (
                                <td key={ranges[k]}>{`${share.toFixed(1)}% (${row.counts[k].toLocaleString()})`}</td>
                            ))}
                            <td>{row.total.toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>
        </div>
    );
}
