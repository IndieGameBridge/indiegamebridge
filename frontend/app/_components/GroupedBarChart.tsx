export type GroupedBarSeries = {
    key: string;
    label: string;
    color: string;
    format: (value: number) => string;
    // Replaces the legend's default "(max ...)" suffix, for charts where the maximum
    // isn't the useful thing to say about a series.
    legendSuffix?: string;
};

export type GroupedBarRow = {
    label: string;
    values: Record<string, number>;
    // Text shown past the bar and in its tooltip, for when the plotted number isn't the
    // whole story - a share that also wants to name the count behind it, say.
    valueLabels?: Record<string, string>;
    // Optional small print under the row's bars, e.g. a game's genres.
    subLabel?: string;
};

type GroupedBarChartProps = {
    // Omit where the surrounding section already names the chart.
    title?: string;
    // Accessible name for the SVG and caption for the mirroring table.
    caption: string;
    description: string;
    // Header for the table's first column, e.g. "Genre" or "Game".
    rowHeader: string;
    series: GroupedBarSeries[];
    rows: GroupedBarRow[];
    // "series" (the default) scales every series against its own maximum, for series
    // that share no usable axis. "shared" puts them all on one axis, for series in the
    // same unit, where the point is comparing them against each other.
    scale?: "series" | "shared";
    note?: string;
};

/**
 * Grouped horizontal bar chart, shared by the per-genre, per-game and peak-viewer
 * distribution charts.
 *
 * Row label in a left gutter, one thin bar per series with its value past the bar's
 * end, and a legend below.
 */
export function GroupedBarChart({
    title,
    caption,
    description,
    rowHeader,
    series,
    rows,
    scale = "series",
    note,
}: GroupedBarChartProps) {
    if (rows.length === 0) return null;

    const maxima = series.map((one_series) =>
        Math.max(...rows.map((row) => row.values[one_series.key] ?? 0), 0),
    );
    const sharedMax = Math.max(...maxima, 0);
    const scaleOf = (j: number) => (scale === "shared" ? sharedMax : maxima[j]);

    const valueLabel = (row: GroupedBarRow, one_series: GroupedBarSeries) =>
        row.valueLabels?.[one_series.key]
        ?? one_series.format(row.values[one_series.key] ?? 0);

    // Fixed coordinate system, matching the genre-trends chart: the SVG keeps a
    // readable pixel size and scrolls horizontally on narrow screens rather than
    // shrinking the labels.
    const width = 1000;
    // Left gutter sized to the longest row label, capped at the width the long genre
    // and game names need, so short labels ("3-5", "201+") don't leave a white band.
    const longestLabel = Math.max(...rows.map((row) => row.label.length));
    const labelWidth = Math.min(180, Math.max(60, longestLabel * 7 + 12));
    // Right gutter sized to the longest value label, so a long one ("61.3% (597,599)")
    // isn't clipped and a chart of short ones doesn't waste the space.
    const longestValue = Math.max(
        ...rows.flatMap((row) => series.map((one_series) => valueLabel(row, one_series).length)),
    );
    const valueWidth = Math.max(90, longestValue * 6 + 12);
    const chartLeft = labelWidth;
    const chartWidth = width - labelWidth - valueWidth;

    // One thin bar per series, stacked with a small gap, then a larger gap before the
    // next row so each row reads as one group.
    const subBarHeight = 12;
    const subBarGap = 3;
    const groupGap = 18;
    const paddingTop = 6;
    const paddingBottom = 6;
    // Reserved for every row once any row carries small print, so the groups stay
    // evenly spaced rather than shifting under a row that happens to have none.
    const subLabelHeight = rows.some((row) => row.subLabel) ? 16 : 0;
    const barsHeight = series.length * subBarHeight + (series.length - 1) * subBarGap;
    const rowHeight = barsHeight + subLabelHeight + groupGap;
    const height = paddingTop + rows.length * rowHeight - groupGap + paddingBottom;

    return (
        <div>
            {title && <h3 className="text-lg font-semibold mb-4">{title}</h3>}

            <div className="overflow-x-auto">
            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={caption}
            >
                <title>{caption}</title>
                <desc>{description}</desc>

                {rows.map((row, i) => {
                    const groupTop = paddingTop + i * rowHeight;
                    // Centred on the bars only, so small print below doesn't drag the
                    // row label out of line with them.
                    const groupCenterY = groupTop + barsHeight / 2;
                    return (
                        <g key={row.label}>
                            {/* Row label, right-aligned against the bars. */}
                            <text
                                x={labelWidth - 10}
                                y={groupCenterY}
                                textAnchor="end"
                                dominantBaseline="central"
                                fontSize="13"
                                className="fill-current selection:fill-white"
                            >
                                {row.label}
                            </text>

                            {series.map((one_series, j) => {
                                const value = row.values[one_series.key] ?? 0;
                                const max = scaleOf(j);
                                // Give any non-zero value at least a 1px sliver so a
                                // small row still shows next to a dominant one.
                                const barW = max > 0 && value > 0
                                    ? Math.max(1, (value / max) * chartWidth)
                                    : 0;
                                const barY = groupTop + j * (subBarHeight + subBarGap);
                                const centerY = barY + subBarHeight / 2;
                                const text = valueLabel(row, one_series);
                                return (
                                    <g key={one_series.key}>
                                        <rect
                                            x={chartLeft}
                                            y={barY}
                                            width={barW}
                                            height={subBarHeight}
                                            fill={one_series.color}
                                        >
                                            <title>{`${row.label} — ${one_series.label}: ${text}`}</title>
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
                                            {text}
                                        </text>
                                    </g>
                                );
                            })}

                            {row.subLabel && (
                                <text
                                    x={chartLeft}
                                    y={groupTop + barsHeight + subLabelHeight / 2}
                                    textAnchor="start"
                                    dominantBaseline="central"
                                    fontSize="10"
                                    className="fill-current selection:fill-white"
                                >
                                    {row.subLabel}
                                </text>
                            )}
                        </g>
                    );
                })}
            </svg>
            </div>

            {/* Legend: colour swatch, series name and either the value the series is
                scaled against or its own suffix. Kept in HTML outside the scroller so it
                stays put and folds onto more lines on narrow screens. */}
            <div className="flex flex-row flex-wrap gap-x-8 gap-y-2 mt-3 text-sm">
                {series.map((one_series, j) => (
                    <div key={`legend-${one_series.key}`} className="flex flex-row items-center gap-2">
                        <span
                            className="inline-block w-[13] h-[13] shrink-0"
                            style={{ backgroundColor: one_series.color }}
                        />
                        <span>
                            {`${one_series.label} ${one_series.legendSuffix ?? `(max ${one_series.format(maxima[j])})`}`}
                        </span>
                    </div>
                ))}
            </div>

            {/* Screen-reader + SEO-friendly table mirroring the chart. */}
            {/* sr-only sits on a wrapper, not on the table: a table box can't shrink
                below its min-content width, so sr-only's width:1px is ignored there and
                the hidden table still widens the page. */}
            <div className="sr-only">
            <table>
                <caption>{caption}</caption>
                <thead>
                    <tr>
                        <th>{rowHeader}</th>
                        {series.map((one_series) => (
                            <th key={one_series.key}>{one_series.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <tr key={row.label}>
                            <td>{row.subLabel ? `${row.label} — ${row.subLabel}` : row.label}</td>
                            {series.map((one_series) => (
                                <td key={one_series.key}>{valueLabel(row, one_series)}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>

            {note && <p className="mt-4 text-sm">{note}</p>}
        </div>
    );
}
