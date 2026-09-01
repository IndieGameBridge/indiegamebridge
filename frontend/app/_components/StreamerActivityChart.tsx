export type StreamerDailyActivity = {
    x: string;
    hours: number;
    peak: number;
    avg: number;
    streams: number;
    weekend: boolean;
    month: string;
};

export type ProfileSeries = {
    key: "hours" | "peak" | "avg";
    label: string;
    color: string;
    format: (value: number) => string;
};

// Okabe-Ito colour-blind-safe palette, same source as the genre-trends chart:
// blue, amber and bluish-green stay distinguishable for the common forms of
// colour blindness and hold contrast on a white background. Shared with the
// per-genre chart so a colour means the same thing in both profile charts.
export const PROFILE_SERIES: ProfileSeries[] = [
    {
        key: "hours",
        label: "Hours streamed",
        color: "#0072B2", // blue
        format: (v) => `${v} h`,
    },
    {
        key: "peak",
        label: "Peak viewers",
        color: "#E69F00", // amber
        format: (v) => v.toLocaleString(),
    },
    {
        key: "avg",
        label: "Avg viewers",
        color: "#009E73", // bluish green
        format: (v) => v.toLocaleString(),
    },
];

// Weekend day labels are picked out in blue so the streaming rhythm
// (weekends-only, weekdays-only, every day) reads without counting columns.
const WEEKEND_LABEL_COLOR = "#0072B2";

// Background for every other month band. The window spans two months as a rule,
// so in practice this shades the older one and leaves the current month plain.
const MONTH_BAND_SHADE = "#f3f4f6";

export function StreamerActivityChart({ daily }: { daily: StreamerDailyActivity[] }) {
    if (daily.length === 0) return null;

    // Each series is scaled against its own maximum. Hours (0-24) and viewers
    // (potentially thousands) share no usable axis, and the chart is read for
    // shape - how regular the schedule is, how steady the audience is - rather
    // than for absolute values, which the legend and tooltips carry instead.
    const maxima = PROFILE_SERIES.map((series) =>
        Math.max(...daily.map((day) => day[series.key]), 0),
    );

    // Bar-first geometry: the bars get a fixed readable width and the chart's total
    // width falls out of the day count, rather than 28 days being squeezed into a
    // fixed canvas. The chart scrolls horizontally instead of shrinking.
    const barWidth = 18;
    const barGap = 2;
    // Gap between days, comfortably wider than the gap inside a day so each day's
    // three bars read as one group.
    const groupGap = 18;
    const barsWidth = PROFILE_SERIES.length * barWidth + (PROFILE_SERIES.length - 1) * barGap;
    const groupWidth = barsWidth + groupGap;
    // Each day's baseline tick overhangs its bars by a couple of pixels on each side.
    const tickOverhang = 3;

    // Grown by barHeadroom so the extra space is added to the plot area rather
    // than taken out of the bars, which keep their previous pixel heights.
    const height = 230;
    const paddingLeft = 8;
    const paddingRight = 8;
    const paddingTop = 8;
    const paddingBottom = 26;
    const chartWidth = daily.length * groupWidth;
    const chartHeight = height - paddingTop - paddingBottom;
    // Breathing room between the tallest bar and the top of the washed plot area,
    // so a full-height bar doesn't sit flush against the ceiling.
    const barHeadroom = 10;
    const barAreaHeight = chartHeight - barHeadroom;
    const width = paddingLeft + chartWidth + paddingRight;

    const baselineY = paddingTop + chartHeight;
    const monthBandHeight = 22;
    const totalHeight = height + monthBandHeight;

    // Days arrive in date order, so each month is one contiguous run of columns.
    const monthRuns: { month: string; start: number; length: number }[] = [];
    for (let i = 0; i < daily.length; i++) {
        const last = monthRuns[monthRuns.length - 1];
        if (last && last.month === daily[i].month) {
            last.length += 1;
        } else {
            monthRuns.push({ month: daily[i].month, start: i, length: 1 });
        }
    }

    return (
        <div>
            <h3 className="text-lg font-semibold mb-4">Hours and viewers per day</h3>

            <div className="overflow-x-auto">
        <svg
            width={width}
            height={totalHeight}
            viewBox={`0 0 ${width} ${totalHeight}`}
            role="img"
            aria-label="Daily streaming activity over the last 4 weeks"
        >
            <title>Daily streaming activity over the last 4 weeks</title>
            <desc>
                Grouped bar chart with one group per calendar day over the last 4 weeks,
                most recent day first, showing hours streamed, peak viewers and average
                viewers. Each series is scaled to its own maximum.
            </desc>

            {/* Plot-area wash: marks where the chart's bounds are without competing
                with the bars. Spans the columns only - not the day labels or legend. */}
            <rect
                x={paddingLeft}
                y={paddingTop}
                width={chartWidth}
                height={chartHeight}
                fill="#f3f4f6"
            />

            {daily.map((day, i) => {
                const groupX = paddingLeft + i * groupWidth + groupGap / 2;
                return (
                    <g key={day.x}>
                        {/* Per-day baseline, sitting just under that day's three bars,
                            so the days stay visually separated even when empty. */}
                        <line
                            x1={groupX - tickOverhang}
                            x2={groupX + barsWidth + tickOverhang}
                            y1={baselineY}
                            y2={baselineY}
                            stroke="#9ca3af"
                        />
                        {PROFILE_SERIES.map((series, j) => {
                            const value = day[series.key];
                            const max = maxima[j];
                            // Give any non-zero value at least a 1px sliver so a short
                            // stream on an otherwise busy month is still visible.
                            const barH = max > 0 && value > 0
                                ? Math.max(1, (value / max) * barAreaHeight)
                                : 0;
                            const barX = groupX + j * (barWidth + barGap);
                            return (
                                <rect
                                    key={series.key}
                                    x={barX}
                                    y={baselineY - barH}
                                    width={barWidth}
                                    height={barH}
                                    fill={series.color}
                                >
                                    <title>{`${day.x} — ${series.label}: ${series.format(value)}`}</title>
                                </rect>
                            );
                        })}
                    </g>
                );
            })}

            {/* X-axis labels: weekday plus day of month, one per day. Weekends are
                picked out; note that fill-current would win over the fill attribute,
                so the class is only applied to weekdays. */}
            {daily.map((day, i) => (
                <text
                    key={`xlabel-${day.x}`}
                    x={paddingLeft + i * groupWidth + groupWidth / 2}
                    y={height - 10}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight={day.weekend ? "bold" : undefined}
                    fill={day.weekend ? WEEKEND_LABEL_COLOR : undefined}
                    className={day.weekend ? "selection:fill-white" : "fill-current selection:fill-white"}
                >
                    {day.x}
                </text>
            ))}

            {/* Month band under the day labels. Alternate runs get a wash so the
                month boundary is visible; the first run - the current month - is
                left plain. */}
            {monthRuns.map((run, i) => {
                const runX = paddingLeft + run.start * groupWidth;
                const runWidth = run.length * groupWidth;
                return (
                    <g key={`month-${run.start}`}>
                        {i % 2 === 1 && (
                            <rect
                                x={runX}
                                y={height}
                                width={runWidth}
                                height={monthBandHeight}
                                fill={MONTH_BAND_SHADE}
                            />
                        )}
                        <text
                            x={runX + runWidth / 2}
                            y={height + monthBandHeight / 2}
                            textAnchor="middle"
                            dominantBaseline="central"
                            fontSize="11"
                            className="fill-current selection:fill-white"
                        >
                            {run.month}
                        </text>
                    </g>
                );
            })}
        </svg>
            </div>

            {/* Legend: a colour swatch, the series name and the value the series is
                scaled against, since the three series don't share an axis. Kept in
                HTML outside the scroller so it stays put while the chart scrolls. */}
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
            {/* sr-only sits on a wrapper, not on the table: a table box can't shrink
                below its min-content width, so sr-only's width:1px is ignored there and
                the hidden table still widens the page. */}
            <div className="sr-only">
            <table>
                <caption>Daily streaming activity over the last 4 weeks</caption>
                <thead>
                    <tr>
                        <th>Day</th>
                        {PROFILE_SERIES.map((series) => (
                            <th key={series.key}>{series.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {daily.map((day) => (
                        <tr key={day.x}>
                            <td>{`${day.x} ${day.month}`}</td>
                            {PROFILE_SERIES.map((series) => (
                                <td key={series.key}>{series.format(day[series.key])}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>
        </div>
    );
}
