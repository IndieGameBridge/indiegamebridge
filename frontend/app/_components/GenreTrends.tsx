type Bar = { x: string; y: number };

export type GenreDiagram = {
    title: string;
    description: string;
    y_label: string;
    bars: Bar[];
};

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
    const { title, description, y_label, bars } = diagram;
    const maxY = Math.max(...bars.map((b) => b.y), 1);

    // Fixed coordinate system; the SVG scales to the container width (w-full),
    // so bars stay proportional on any screen without horizontal scrolling.
    const width = 1000;
    const rowHeight = 30;
    const barHeight = 18;
    const paddingTop = 6;
    const paddingBottom = 6;
    // Left gutter holds genre names; right gutter holds the value label that sits
    // just past each bar's end.
    const labelWidth = 180;
    const valueWidth = 90;
    const chartLeft = labelWidth;
    const chartWidth = width - labelWidth - valueWidth;
    const height = paddingTop + paddingBottom + bars.length * rowHeight;

    return (
        <div className="col-span-1">
            <h3 className="text-lg font-semibold mb-4">{title}</h3>

            <svg
                width={width}
                height={height}
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={title}
                className="w-full h-auto"
            >
                <title>{title}</title>
                <desc>{`Horizontal bar chart of ${y_label.toLowerCase()} per genre over the last 4 weeks.`}</desc>

                {bars.map((bar, i) => {
                    const rowY = paddingTop + i * rowHeight;
                    const barY = rowY + (rowHeight - barHeight) / 2;
                    const barW = (bar.y / maxY) * chartWidth;
                    const centerY = barY + barHeight / 2;
                    return (
                        <g key={bar.x}>
                            {/* Genre name, right-aligned against the bars. */}
                            <text
                                x={labelWidth - 10}
                                y={centerY}
                                textAnchor="end"
                                dominantBaseline="central"
                                fontSize="13"
                                className="fill-current"
                            >
                                {bar.x}
                            </text>
                            <rect
                                x={chartLeft}
                                y={barY}
                                width={barW}
                                height={barHeight}
                                className="fill-indigo-500"
                            />
                            {/* Value, just past the bar's end. */}
                            <text
                                x={chartLeft + barW + 6}
                                y={centerY}
                                textAnchor="start"
                                dominantBaseline="central"
                                fontSize="12"
                                className="fill-current"
                            >
                                {bar.y.toLocaleString()}
                            </text>
                        </g>
                    );
                })}
            </svg>

            <p className="mt-4 text-sm opacity-80">{description}</p>
        </div>
    );
}
