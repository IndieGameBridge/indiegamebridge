import { serverFetch } from "../_lib/server-fetch";
import { LANGUAGE_COLORS, FALLBACK_COLOR } from "./GenreTrends";
import { GroupedBarChart, GroupedBarRow, GroupedBarSeries } from "./GroupedBarChart";

type Bucket = { x: string; y: number };

type DistributionData = {
    title: string;
    description: string;
    buckets: Record<string, Bucket[]>;
};

// Display order for the series. Defined here (not driven by the API response)
// because JSONB storage doesn't preserve key insertion order, so iterating
// data.buckets directly would render alphabetically (de, en, es, fr).
const LANGUAGES: { code: string; label: string }[] = [
    { code: "en", label: "English" },
    { code: "fr", label: "French" },
    { code: "de", label: "German" },
    { code: "es", label: "Spanish" },
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
            <div className="max-w-[1000] mx-auto pt-12 pb-24">
                <h2 className="text-2xl font-bold mb-8">{data.title}</h2>
                <p className="mb-12">{data.description}</p>

                <DistributionChart title={data.title} buckets={data.buckets} />
            </div>
        </section>
    );
}


type ChartProps = {
    title: string;
    buckets: Record<string, Bucket[]>;
};

function DistributionChart({ title, buckets }: ChartProps) {
    // Only languages the payload actually carries; the rest drop out silently.
    const languages = LANGUAGES.filter((lang) => buckets[lang.code]?.length);
    if (languages.length === 0) return null;

    // Every language uses the same bucket list, so the first one defines the rows.
    const bucketLabels = buckets[languages[0].code].map((bucket) => bucket.x);

    const totals: Record<string, number> = {};
    for (const lang of languages) {
        totals[lang.code] = buckets[lang.code].reduce((sum, bucket) => sum + bucket.y, 0);
    }

    // Plotted as each language's share of its own streamers, not as raw counts: English
    // outnumbers the others roughly ten to one, so on a shared count axis the other
    // three would be slivers. Shares put the four distributions side by side; the counts
    // ride along in each bar's label and the totals sit in the legend, so the equal-looking
    // bars aren't misread as equal audiences.
    const share = (code: string, i: number) =>
        totals[code] > 0 ? (buckets[code][i].y / totals[code]) * 100 : 0;

    const series: GroupedBarSeries[] = languages.map((lang) => ({
        key: lang.code,
        label: lang.label,
        color: LANGUAGE_COLORS[lang.code] ?? FALLBACK_COLOR,
        format: (value) => `${value.toFixed(1)}%`,
        legendSuffix: `(${totals[lang.code].toLocaleString()} streamers)`,
    }));

    const rows: GroupedBarRow[] = bucketLabels.map((label, i) => ({
        label,
        values: Object.fromEntries(languages.map((lang) => [lang.code, share(lang.code, i)])),
        valueLabels: Object.fromEntries(languages.map((lang) => [
            lang.code,
            `${share(lang.code, i).toFixed(1)}% (${buckets[lang.code][i].y.toLocaleString()})`,
        ])),
    }));

    return (
        <GroupedBarChart
            caption={title}
            description={
                "Horizontal bar chart with one group per peak-viewer bucket and one bar per" +
                " broadcast language, showing the share of that language's streamers whose" +
                " peak viewer count falls in the bucket. All languages share one axis."
            }
            rowHeader="Peak viewers"
            series={series}
            rows={rows}
            // Shares are the same unit across languages, and comparing them is the
            // whole point of the chart, so they belong on one axis.
            scale="shared"
        />
    );
}
