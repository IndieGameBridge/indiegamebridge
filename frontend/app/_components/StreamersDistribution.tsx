import { serverFetch } from "../_lib/server-fetch";

type Bucket = { x: string; y: number };

type DistributionData = {
    title: string;
    description: string;
    buckets: Record<string, Bucket[]>;
};

// Display order for the charts. Defined here (not driven by the API response)
// because JSONB storage doesn't preserve key insertion order, so iterating
// data.buckets directly would render alphabetically (de, en, fr).
const LANGUAGES: { code: string; label: string }[] = [
    { code: "en", label: "English" },
    { code: "fr", label: "French" },
    { code: "de", label: "German" },
];

export async function StreamersDistribution() {
    const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
    const response = await serverFetch(`${apiBase}/streamers/distribution/`);

    if (!response.ok) {
        return null;
    }

    const data: DistributionData = await response.json();

    return (
        <section className="px-6">
            <div className="max-w-[1000] mx-auto py-16">
                <h2 className="text-2xl font-bold mb-4">{data.title}</h2>
                <p className="mb-6">{data.description}</p>

                <div className="grid grid-cols-1 gap-6">
                    {LANGUAGES.map(({ code, label }) => {
                        const buckets = data.buckets[code];
                        if (!buckets) return null;
                        return (
                            <DistributionChart
                                key={code}
                                title={label}
                                buckets={buckets}
                            />
                        );
                    })}
                </div>
            </div>
        </section>
    );
}


type ChartProps = {
    title: string;
    buckets: Bucket[];
};

function DistributionChart({ title, buckets }: ChartProps) {
    const maxY = Math.max(...buckets.map((b) => b.y), 1);
    const totalStreamers = buckets.reduce((sum, b) => sum + b.y, 0);

    // viewBox-relative units; SVG scales with container width via w-full h-auto.
    const width = 1000;
    const height = 250;
    const paddingLeft = 36;
    const paddingRight = 8;
    // Extra top padding leaves room for per-bar value labels above the tallest bar.
    const paddingTop = 22;
    const paddingBottom = 28;
    const chartWidth = width - paddingLeft - paddingRight;
    const chartHeight = height - paddingTop - paddingBottom;

    const barGap = 2;
    const barWidth = (chartWidth - barGap * (buckets.length - 1)) / buckets.length;

    return (
        <div className="col-span-1">
            <h3 className="text-lg font-semibold mb-1">{title}</h3>
            <p className="text-xs mb-2">{totalStreamers.toLocaleString()} streamers</p>

            <svg
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={`${title} streamer peak-viewer distribution`}
                className="w-full h-auto"
            >
                <title>{`${title} streamer peak-viewer distribution`}</title>
                <desc>
                    {`Bar chart showing how many ${title} streamers fall into each peak-viewer bucket over the time window.`}
                </desc>

                {/* Baseline (per-bar value labels above each bar make a full y-axis redundant). */}
                <line
                    x1={paddingLeft}
                    x2={paddingLeft + chartWidth}
                    y1={paddingTop + chartHeight}
                    y2={paddingTop + chartHeight}
                    stroke="#e5e7eb"
                />

                {/* Bars. */}
                {buckets.map((bucket, i) => {
                    const barX = paddingLeft + i * (barWidth + barGap);
                    const barH = (bucket.y / maxY) * chartHeight;
                    const barY = paddingTop + chartHeight - barH;
                    return (
                        <rect
                            key={bucket.x}
                            x={barX}
                            y={barY}
                            width={barWidth}
                            height={barH}
                            className="fill-indigo-500"
                        />
                    );
                })}

                {/* Per-bar value labels (sit above each bar's top edge). */}
                {buckets.map((bucket, i) => {
                    const barX = paddingLeft + i * (barWidth + barGap) + barWidth / 2;
                    const barH = (bucket.y / maxY) * chartHeight;
                    const barY = paddingTop + chartHeight - barH;
                    return (
                        <text
                            key={`value-${bucket.x}`}
                            x={barX}
                            y={barY - 4}
                            textAnchor="middle"
                            fontSize="12"
                            className="selection:fill-white"
                        >
                            {bucket.y.toLocaleString()}
                        </text>
                    );
                })}

                {/* X-axis labels (one per bucket). */}
                {buckets.map((bucket, i) => {
                    const barX = paddingLeft + i * (barWidth + barGap) + barWidth / 2;
                    return (
                        <text
                            key={`xlabel-${bucket.x}`}
                            x={barX}
                            y={height - 10}
                            textAnchor="middle"
                            fontSize="12"
                            className="selection:fill-white"
                        >
                            {bucket.x}
                        </text>
                    );
                })}
            </svg>

            {/* Screen-reader + SEO-friendly data table mirroring the chart. */}
            <table className="sr-only">
                <caption>{`${title} streamer peak-viewer distribution`}</caption>
                <thead>
                    <tr>
                        <th>Peak viewers</th>
                        <th>Streamers</th>
                    </tr>
                </thead>
                <tbody>
                    {buckets.map((bucket) => (
                        <tr key={bucket.x}>
                            <td>{bucket.x}</td>
                            <td>{bucket.y.toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
