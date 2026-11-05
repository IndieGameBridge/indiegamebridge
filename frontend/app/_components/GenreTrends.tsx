type LanguageMeta = { code: string; label: string };
type GenreBar = { x: string; values: Record<string, number> };

export type GenreDiagram = {
    title: string;
    description: string;
    // Shown only where the languages are added up.
    overview_note?: string;
    y_label: string;
    languages: LanguageMeta[];
    bars: GenreBar[];
};

// One series per chart, in the blue the site's other charts give their first series.
const BAR_COLOR = "#0072B2";

/**
 * The Genre Trends diagrams for one page: one language's numbers, or with no language,
 * every language's added up. Each diagram ranks the genres by that page's own numbers.
 */
export function GenreTrends({ diagrams, language }: { diagrams: GenreDiagram[]; language: LanguageMeta | null }) {
    return (
        <div className="grid grid-cols-1 gap-24">
            {diagrams.map((diagram) => (
                <GenreDiagramChart key={diagram.title} diagram={diagram} language={language} />
            ))}
        </div>
    );
}


function GenreDiagramChart({ diagram, language }: { diagram: GenreDiagram; language: LanguageMeta | null }) {
    const { title, description, overview_note, y_label, languages, bars } = diagram;
    const total = (bar: GenreBar) =>
        languages.reduce((sum, lang) => sum + (bar.values[lang.code] ?? 0), 0);
    // Highest first. The sort is stable, so ties keep the payload's order, which is by
    // every language's total.
    const rows = bars
        .map((bar) => ({ bar, value: language ? bar.values[language.code] ?? 0 : total(bar) }))
        .sort((a, b) => b.value - a.value);
    const maxY = Math.max(...rows.map((row) => row.value), 1);
    const scope = language ? `${language.label}-language streams` : "all languages added up";

    // Fixed coordinate system; the SVG keeps a readable pixel size and scrolls
    // horizontally on narrow screens (see the overflow-x-auto wrapper) rather than
    // shrinking the bars and labels.
    const width = 1000;
    // Left gutter holds genre names; right gutter holds the value label past each bar.
    const labelWidth = 180;
    const valueWidth = 90;
    const chartLeft = labelWidth;
    const chartWidth = width - labelWidth - valueWidth;

    const barHeight = 14;
    const rowGap = 8;
    const paddingTop = 4;
    const rowHeight = barHeight + rowGap;
    // The trailing row gap doubles as the chart's bottom padding.
    const height = paddingTop + rows.length * rowHeight;

    return (
        <div className="col-span-1">
            <h3 className="text-lg font-semibold mb-4">{title}</h3>

            <div className="overflow-x-auto">
            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={`${title}, ${scope}`}
            >
                <title>{`${title}, ${scope}`}</title>
                <desc>{`Horizontal bar chart of ${y_label.toLowerCase()} per genre over the last 4 weeks, ${scope}, highest first.`}</desc>

                {rows.map(({ bar, value }, i) => {
                    const barY = paddingTop + i * rowHeight;
                    const centerY = barY + barHeight / 2;
                    // Give any non-zero value at least a 1px sliver so a small genre
                    // still shows next to a dominant one.
                    const barW = value > 0 ? Math.max(1, (value / maxY) * chartWidth) : 0;
                    return (
                        <g key={bar.x}>
                            {/* Genre name, right-aligned against the bar. */}
                            <text
                                x={labelWidth - 10}
                                y={centerY}
                                textAnchor="end"
                                dominantBaseline="central"
                                fontSize="13"
                                className="fill-current selection:fill-white"
                            >
                                {bar.x}
                            </text>
                            <rect x={chartLeft} y={barY} width={barW} height={barHeight} fill={BAR_COLOR}>
                                <title>{`${bar.x}: ${value.toLocaleString()}`}</title>
                            </rect>
                            {/* Value, just past the bar's end. */}
                            <text
                                x={chartLeft + barW + 6}
                                y={centerY}
                                textAnchor="start"
                                dominantBaseline="central"
                                fontSize="11"
                                className="fill-current selection:fill-white"
                            >
                                {value.toLocaleString()}
                            </text>
                        </g>
                    );
                })}
            </svg>
            </div>

            <p className="mt-4 text-sm">
                {description}
                {!language && overview_note && ` ${overview_note}`}
            </p>

            {language ? (
                // Screen-reader + SEO-friendly table mirroring the chart. sr-only sits on
                // a wrapper, not on the table: a table box can't shrink below its
                // min-content width, so sr-only's width:1px is ignored there and the
                // hidden table still widens the page.
                <div className="sr-only">
                <table>
                    <caption>{`${title}, ${scope}`}</caption>
                    <thead>
                        <tr>
                            <th>Genre</th>
                            <th>{y_label}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(({ bar, value }) => (
                            <tr key={bar.x}>
                                <td>{bar.x}</td>
                                <td>{value.toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                </div>
            ) : (
                // The overview's chart adds the languages up; the table under it keeps each
                // language's numbers side by side.
                <div className="overflow-x-auto mt-8 text-sm">
                <table className="border-collapse">
                    <caption className="text-left font-semibold pb-2">{`${title}, by language`}</caption>
                    <thead>
                        <tr>
                            <th className="text-left font-semibold pr-4 py-1">Genre</th>
                            {languages.map((lang) => (
                                <th key={lang.code} className="text-right font-semibold px-2 py-1">{lang.label}</th>
                            ))}
                            <th className="text-right font-semibold pl-2 py-1">All</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(({ bar, value }) => (
                            <tr key={bar.x} className="border-t border-gray-200">
                                <td className="text-left pr-4 py-1 whitespace-nowrap">{bar.x}</td>
                                {languages.map((lang) => (
                                    <td key={lang.code} className="text-right px-2 py-1 tabular-nums">
                                        {(bar.values[lang.code] ?? 0).toLocaleString()}
                                    </td>
                                ))}
                                <td className="text-right pl-2 py-1 tabular-nums">{value.toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                </div>
            )}
        </div>
    );
}
