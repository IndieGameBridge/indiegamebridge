import { PROFILE_SERIES } from "./StreamerActivityChart";

export type StreamerGenreActivity = {
    x: string;
    hours: number;
    peak: number;
    avg: number;
};

export function StreamerGenreChart({ genres }: { genres: StreamerGenreActivity[] }) {
    if (genres.length === 0) return null;

    // Scaled per series, like the daily chart: hours and viewer counts share no usable
    // axis, so each series is measured against its own maximum and the legend carries
    // that maximum. Bars compare across genres within a series, not between series.
    const maxima = PROFILE_SERIES.map((series) =>
        Math.max(...genres.map((genre) => genre[series.key]), 0),
    );

    // Fixed coordinate system, matching the genre-trends chart: genre names sit in a
    // left gutter, the value label past each bar's end, and the SVG scrolls
    // horizontally on narrow screens rather than shrinking the labels.
    const width = 1000;
    const labelWidth = 180;
    const valueWidth = 90;
    const chartLeft = labelWidth;
    const chartWidth = width - labelWidth - valueWidth;

    // One thin bar per series, stacked with a small gap, then a larger gap before the
    // next genre so each genre reads as one group.
    const subBarHeight = 12;
    const subBarGap = 3;
    const groupGap = 18;
    const paddingTop = 6;
    const paddingBottom = 6;
    const groupHeight =
        PROFILE_SERIES.length * subBarHeight + (PROFILE_SERIES.length - 1) * subBarGap;
    const rowHeight = groupHeight + groupGap;
    const height = paddingTop + genres.length * rowHeight - groupGap + paddingBottom;

    return (
        <div>
            <h3 className="text-lg font-semibold mb-4">Hours and viewers per genre</h3>

            <div className="overflow-x-auto">
            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label="Hours streamed and viewers per genre over the last 4 weeks"
            >
                <title>Hours streamed and viewers per genre over the last 4 weeks</title>
                <desc>
                    Horizontal bar chart with one group per game genre over the last 4 weeks,
                    most-streamed genre first, showing hours streamed, peak viewers and
                    average viewers. Each series is scaled to its own maximum.
                </desc>

                {genres.map((genre, i) => {
                    const groupTop = paddingTop + i * rowHeight;
                    const groupCenterY = groupTop + groupHeight / 2;
                    return (
                        <g key={genre.x}>
                            {/* Genre name, right-aligned against the bars and centred
                                vertically across the group's three bars. */}
                            <text
                                x={labelWidth - 10}
                                y={groupCenterY}
                                textAnchor="end"
                                dominantBaseline="central"
                                fontSize="13"
                                className="fill-current selection:fill-white"
                            >
                                {genre.x}
                            </text>

                            {PROFILE_SERIES.map((series, j) => {
                                const value = genre[series.key];
                                const max = maxima[j];
                                // Give any non-zero value at least a 1px sliver so a
                                // briefly played genre still shows next to a dominant one.
                                const barW = max > 0 && value > 0
                                    ? Math.max(1, (value / max) * chartWidth)
                                    : 0;
                                const barY = groupTop + j * (subBarHeight + subBarGap);
                                const centerY = barY + subBarHeight / 2;
                                return (
                                    <g key={series.key}>
                                        <rect
                                            x={chartLeft}
                                            y={barY}
                                            width={barW}
                                            height={subBarHeight}
                                            fill={series.color}
                                        >
                                            <title>{`${genre.x} — ${series.label}: ${series.format(value)}`}</title>
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
                                            {series.format(value)}
                                        </text>
                                    </g>
                                );
                            })}
                        </g>
                    );
                })}
            </svg>
            </div>

            {/* Legend: colour swatch, series name and the value the series is scaled
                against. Kept in HTML outside the scroller so it stays put. */}
            <div className="flex flex-row flex-wrap gap-x-8 gap-y-2 mt-3 text-sm">
                {PROFILE_SERIES.map((series, j) => (
                    <div key={`legend-${series.key}`} className="flex flex-row items-center gap-2">
                        <span
                            className="inline-block w-[13] h-[13] shrink-0"
                            style={{ backgroundColor: series.color }}
                        />
                        <span>{`${series.label} (max ${series.format(maxima[j])})`}</span>
                    </div>
                ))}
            </div>

            {/* Screen-reader + SEO-friendly table mirroring the chart. */}
            <table className="sr-only">
                <caption>Hours streamed and viewers per genre over the last 4 weeks</caption>
                <thead>
                    <tr>
                        <th>Genre</th>
                        {PROFILE_SERIES.map((series) => (
                            <th key={series.key}>{series.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {genres.map((genre) => (
                        <tr key={genre.x}>
                            <td>{genre.x}</td>
                            {PROFILE_SERIES.map((series) => (
                                <td key={series.key}>{series.format(genre[series.key])}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* A game's time counts toward each of its genres, so the bars deliberately
                total more than the streamer's hours; said here rather than left to be
                inferred from bars that don't add up. */}
            <p className="mt-4 text-sm">
                A game counts toward every genre it carries, so genres overlap and the hours
                add up to more than the total hours streamed.
            </p>
        </div>
    );
}
