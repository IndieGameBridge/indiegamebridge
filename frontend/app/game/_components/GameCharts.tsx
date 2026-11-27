// A game page's numbers: its tiles, its bars of shares, and its hours of the day. Plain HTML,
// drawn on the server; each bar's numbers show on hover and to screen readers.

// The profile charts' blue.
const BAR_COLOR = "#0072B2";

export type StatTile = { label: string; value: string };

export type ShareBar = {
    label: string;
    // 0 to 1: the bar's length.
    share: number;
    // The share or count as the bar's end says it, e.g. "61%" or "1,167".
    value: string;
    // The baseline's share, drawn as a tick; null or absent for none.
    baseline?: number | null;
};

export type ShareBarsContent = { title: string; caption: string; bars: ShareBar[] };

export type HourBarsContent = {
    title: string;
    caption: string;
    // The chart in words, for screen readers.
    summary: string;
    bars: { label: string; share: number; value: string }[];
    axis: string[];
};

export function StatTiles({ tiles }: { tiles: StatTile[] }) {
    return (
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
            {tiles.map((tile) => (
                <div key={tile.label} className="min-w-0 border border-gray-300 rounded-lg p-4 md:p-5">
                    <div className="text-sm text-gray-600">{tile.label}</div>
                    <div className="text-xl sm:text-2xl md:text-3xl font-bold text-brand-blue tabular-nums wrap-anywhere">
                        {tile.value}
                    </div>
                </div>
            ))}
        </section>
    );
}

function percent(share: number): string {
    return `${Math.round(share * 100)}%`;
}

/** Horizontal bars, each with its share and, where there's one, a dark tick at the baseline's. */
export function ShareBars({ content, labelWidth, className = "", heading = "h2" }: {
    content: ShareBarsContent;
    // Tailwind width of the label column, e.g. "w-16".
    labelWidth: string;
    className?: string;
    // "h3" inside a section of its own, such as the month by month one.
    heading?: "h2" | "h3";
}) {
    return (
        <section className={`min-w-0 ${className}`}>
            {heading === "h3"
                ? <h3 className="text-lg font-bold mb-2">{content.title}</h3>
                : <h2 className="text-xl font-bold mb-2">{content.title}</h2>}
            <p className="text-sm text-gray-600 mb-5">{content.caption}</p>
            <ul className="flex flex-col gap-3">
                {content.bars.map((bar) => {
                    const against = bar.baseline != null ? ` (against ${percent(bar.baseline)})` : "";
                    return (
                        <li key={bar.label} className="flex items-center gap-3" title={`${bar.label}: ${bar.value}${against}`}>
                            <span className={`${labelWidth} shrink-0 text-sm`}>{bar.label}</span>
                            <div className="relative flex-1 h-3.5 bg-gray-200 rounded-[3px]" aria-hidden="true">
                                <div
                                    className="h-full rounded-[3px]"
                                    // A share too small to see still shows as a sliver.
                                    style={{ width: `${bar.share > 0 ? Math.max(bar.share * 100, 0.5) : 0}%`, backgroundColor: BAR_COLOR }}
                                />
                                {bar.baseline != null && (
                                    <div
                                        className="absolute -top-0.75 w-0.5 h-5 bg-gray-900"
                                        style={{ left: `min(calc(100% - 2px), ${bar.baseline * 100}%)` }}
                                    />
                                )}
                            </div>
                            <span className="w-14 shrink-0 text-right text-sm tabular-nums">
                                {bar.value}
                                {against && <span className="sr-only">{against}</span>}
                            </span>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}

/** The 24 hours of the day, UTC, each as a column as tall as its share of the game's streaming. */
export function HourBars({ content }: { content: HourBarsContent }) {
    const top = Math.max(...content.bars.map((bar) => bar.share)) || 1;
    return (
        <section>
            <h2 className="text-xl font-bold mb-2">{content.title}</h2>
            <p className="text-sm text-gray-600 mb-5">{content.caption}</p>
            <div role="img" aria-label={content.summary} className="flex items-end gap-0.5 sm:gap-1 h-25 border-b border-gray-400">
                {content.bars.map((bar) => (
                    <div
                        key={bar.label}
                        title={`${bar.label}: ${bar.value}`}
                        className="flex-1 h-full flex items-end hover:bg-gray-100"
                    >
                        <div
                            className="w-full rounded-t-[3px]"
                            style={{ height: `${(bar.share / top) * 100}%`, backgroundColor: BAR_COLOR }}
                        />
                    </div>
                ))}
            </div>
            <div className="flex justify-between text-xs text-gray-600 pt-1.5" aria-hidden="true">
                {content.axis.map((label) => <span key={label}>{label}</span>)}
            </div>
        </section>
    );
}
