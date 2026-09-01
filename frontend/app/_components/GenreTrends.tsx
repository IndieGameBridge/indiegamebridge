type LanguageMeta = { code: string; label: string };
type GenreBar = { x: string; values: Record<string, number> };

export type GenreDiagram = {
    title: string;
    description: string;
    y_label: string;
    languages: LanguageMeta[];
    bars: GenreBar[];
};

// Per-language bar colours. These are from the Okabe-Ito colour-blind-safe palette:
// blue, bluish-green, amber and reddish-purple. Amber replaces a pure yellow because
// yellow has poor contrast on a white background, and reddish-purple is preferred over
// the palette's vermillion because vermillion sits too close to amber; the four stay
// distinguishable for the common forms of colour blindness. Keyed by ISO 639-1 code
// (matches the backend legend codes).
export const LANGUAGE_COLORS: Record<string, string> = {
    en: "#0072B2", // blue
    fr: "#00cb29", // bluish green
    de: "#00dbe6", // amber
    es: "#ce0c78", // reddish purple
};
export const FALLBACK_COLOR = "#6b7280";

export function GenreTrends({ diagrams }: { diagrams: GenreDiagram[] }) {
    return (
        <div className="grid grid-cols-1 gap-24">
            {diagrams.map((diagram) => (
                <GenreDiagramChart key={diagram.title} diagram={diagram} />
            ))}
        </div>
    );
}


function GenreDiagramChart({ diagram }: { diagram: GenreDiagram }) {
    const { title, description, y_label, languages, bars } = diagram;
    const maxY = Math.max(
        ...bars.flatMap((bar) => languages.map((lang) => bar.values[lang.code] ?? 0)),
        1,
    );

    // Fixed coordinate system; the SVG keeps a readable pixel size and scrolls
    // horizontally on narrow screens (see the overflow-x-auto wrapper) rather than
    // shrinking the bars and labels.
    const width = 1000;
    // Left gutter holds genre names; right gutter holds the value label past each bar.
    const labelWidth = 180;
    const valueWidth = 90;
    const chartLeft = labelWidth;
    const chartWidth = width - labelWidth - valueWidth;

    // Each genre is a group of one thin bar per language, stacked with a small gap,
    // then a larger gap before the next genre.
    const subBarHeight = 12;
    const subBarGap = 3;
    const groupGap = 16;
    const paddingTop = 6;
    const groupHeight =
        languages.length * subBarHeight + Math.max(0, languages.length - 1) * subBarGap;
    const rowHeight = groupHeight + groupGap;

    // The trailing group gap doubles as the chart's bottom padding.
    const height = paddingTop + bars.length * rowHeight;

    return (
        <div className="col-span-1">
            <h3 className="text-lg font-semibold mb-4">{title}</h3>

            <div className="overflow-x-auto">
            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={title}
            >
                <title>{title}</title>
                <desc>{`Horizontal bar chart of ${y_label.toLowerCase()} per genre over the last 4 weeks, split by broadcast language.`}</desc>

                {bars.map((bar, i) => {
                    const groupTop = paddingTop + i * rowHeight;
                    const groupCenterY = groupTop + groupHeight / 2;
                    return (
                        <g key={bar.x}>
                            {/* Genre name, right-aligned against the bars and centred
                                vertically across the group's language bars. */}
                            <text
                                x={labelWidth - 10}
                                y={groupCenterY}
                                textAnchor="end"
                                dominantBaseline="central"
                                fontSize="13"
                                className="fill-current selection:fill-white"
                            >
                                {bar.x}
                            </text>

                            {languages.map((lang, j) => {
                                const value = bar.values[lang.code] ?? 0;
                                const barY = groupTop + j * (subBarHeight + subBarGap);
                                const barW = (value / maxY) * chartWidth;
                                const centerY = barY + subBarHeight / 2;
                                const color = LANGUAGE_COLORS[lang.code] ?? FALLBACK_COLOR;
                                return (
                                    <g key={lang.code}>
                                        <rect
                                            x={chartLeft}
                                            y={barY}
                                            width={barW}
                                            height={subBarHeight}
                                            fill={color}
                                        >
                                            <title>{`${lang.label}: ${value.toLocaleString()}`}</title>
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
                        </g>
                    );
                })}
            </svg>
            </div>

            {/* Legend: a colour swatch + language name per series. Kept in HTML outside
                the scroller so it stays put and folds onto more lines on narrow screens. */}
            <div className="flex flex-row flex-wrap gap-x-8 gap-y-2 mt-3 text-sm">
                {languages.map((lang) => (
                    <div key={`legend-${lang.code}`} className="flex flex-row items-center gap-2">
                        <span
                            className="inline-block w-[13] h-[13] shrink-0"
                            style={{ backgroundColor: LANGUAGE_COLORS[lang.code] ?? FALLBACK_COLOR }}
                        />
                        <span>{lang.label}</span>
                    </div>
                ))}
            </div>

            {/* Screen-reader + SEO-friendly table mirroring the chart. */}
            {/* sr-only sits on a wrapper, not on the table: a table box can't shrink
                below its min-content width, so sr-only's width:1px is ignored there and
                the hidden table still widens the page. */}
            <div className="sr-only">
            <table>
                <caption>{title}</caption>
                <thead>
                    <tr>
                        <th>Genre</th>
                        {languages.map((lang) => (
                            <th key={lang.code}>{lang.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {bars.map((bar) => (
                        <tr key={bar.x}>
                            <td>{bar.x}</td>
                            {languages.map((lang) => (
                                <td key={lang.code}>
                                    {(bar.values[lang.code] ?? 0).toLocaleString()}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>

            <p className="mt-4 text-sm">{description}</p>
        </div>
    );
}
