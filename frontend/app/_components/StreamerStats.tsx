export type StreamerStatsData = {
    peak_viewers: number;
    avg_viewers: number;
    streams_count: number;
    hours_streamed: number;
    genres: string[];
    // Only where a saved list mixes languages: the one these stats are in.
    language?: string;
    // The days of the last 28 with a stream, as days ago: 0 is today. Absent from a
    // cached page until its text is rebuilt with it.
    days_ago?: number[];
    // The UTC date days_ago counts back from, e.g. "2026-11-25". Absent from a cached page
    // until its text is rebuilt with it, and the strip then goes without its weekend line.
    today?: string;
};

// As on a profile's chart: today and the 27 days before it, newest first.
const STRIP_DAYS = 28;
// The site's charts' first blue, on the grey of an empty day.
const STREAMED_COLOR = "#0072B2";
const EMPTY_COLOR = "#e5e7eb";
// The line under each day: Okabe-Ito's bluish green picks out a Saturday or Sunday from a
// weekday's grey, for every kind of colour vision.
const WEEKEND_COLOR = "#009E73";
const WEEKDAY_COLOR = "#d1d5db";

const DAY_MS = 86_400_000;
// Named here rather than by Intl, so the server's text and the browser's always match.
const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// E.g. "Sat 21 Nov", as on a game's chart.
const dayName = (date: Date) => `${WEEKDAY_NAMES[date.getUTCDay()]} ${date.getUTCDate()} ${MONTH_NAMES[date.getUTCMonth()]}`;

// Fills the width it's given, with a wider gap between the weeks, so a weekly rhythm reads
// without counting. A line under each day marks the weekends.
function DayStrip({ days_ago, today }: { days_ago: number[]; today?: string }) {
    const streamed = new Set(days_ago);
    // Midnight UTC of today: a bare "2026-11-25" parses as UTC.
    const start = today ? Date.parse(today) : NaN;
    const days = Array.from({ length: STRIP_DAYS }, (_, day) => {
        const date = Number.isNaN(start) ? null : new Date(start - day * DAY_MS);
        const weekend = date !== null && (date.getUTCDay() === 0 || date.getUTCDay() === 6);
        return { day, date, weekend, filled: streamed.has(day) };
    });
    const weekendsStreamed = days.filter((one) => one.filled && one.weekend).length;

    return (
        <div
            role="img"
            aria-label={`Streamed on ${days_ago.length} of the last ${STRIP_DAYS} days`
                + (Number.isNaN(start) ? "" : `, ${weekendsStreamed} of them on a weekend`)}
            className="flex gap-0.5 mt-1"
        >
            {days.map(({ day, date, weekend, filled }) => (
                <span
                    key={day}
                    title={date ? `${dayName(date)}: ${filled ? "streamed" : "no stream"}` : undefined}
                    className={`flex-1 flex flex-col gap-0.5 ${day > 0 && day % 7 === 0 ? "ml-1" : ""}`}
                >
                    <span className="h-4 rounded-[1px]" style={{ backgroundColor: filled ? STREAMED_COLOR : EMPTY_COLOR }} />
                    {date && <span className="h-0.75" style={{ backgroundColor: weekend ? WEEKEND_COLOR : WEEKDAY_COLOR }} />}
                </span>
            ))}
        </div>
    );
}

// A streamer's last-4-week numbers and genres. Shared by search results and
// saved lists, so a list shows its streamers the way the search did.
export function StreamerStats({ stats }: { stats: StreamerStatsData }) {
    return (
        <div className="border-gray-300 border-t text-sm grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2">
            <div className="mb-4 pt-4">
                <div className="flex flex-col gap-1">
                    <div className="text-nowrap py-1">
                        <span className="text-brand-blue uppercase">Peak: </span>
                        <span>{stats.peak_viewers.toLocaleString()} viewers</span>
                    </div>
                    <div className="text-nowrap py-1">
                        <span className="text-brand-blue uppercase">Avg: </span>
                        <span>{stats.avg_viewers.toLocaleString()} viewers</span>
                    </div>
                    <div className="text-nowrap py-1">
                        <span className="text-brand-blue uppercase">Activity: </span>
                        <span>{stats.streams_count.toLocaleString()} {stats.streams_count > 1 ? 'streams' : 'stream'} • {stats.hours_streamed.toLocaleString()} h</span>
                    </div>
                    {stats.language && (
                        <div className="text-nowrap py-1">
                            <span className="text-brand-blue uppercase">Language: </span>
                            <span>{stats.language}</span>
                        </div>
                    )}
                    {stats.days_ago && (
                        <div className="@container py-1 md:pr-4">
                            {/* The line's key sits beside the label where the strip is 384px or wider, room
                                for both even at "28 of the last 28", and under it otherwise, so every row of
                                a page lays out alike. */}
                            <div className="flex flex-col @sm:flex-row @sm:items-baseline @sm:justify-between @sm:gap-x-4">
                                <div>
                                    <span className="text-brand-blue uppercase">Days streamed: </span>
                                    <span>{stats.days_ago.length} of the last {STRIP_DAYS}</span>
                                </div>
                                {stats.today && (
                                    <span className="text-xs text-gray-600 whitespace-nowrap">
                                        <i aria-hidden="true" className="inline-block w-4 h-0.75 mr-1.5 align-middle" style={{ backgroundColor: WEEKEND_COLOR }} />
                                        Weekend
                                    </span>
                                )}
                            </div>
                            <DayStrip days_ago={stats.days_ago} today={stats.today} />
                        </div>
                    )}
                </div>
            </div>
            <div className="flex flex-row flex-wrap content-start col-span-1 gap-1 md:col-span-1 lg:col-span-1 md:p-4 md:border-l md:border-l-gray-300 lg:p-4 lg:border-l lg:border-l-gray-300">{
                stats.genres.map((genre_name, genre_index) => (
                    <div key={`streamer-genre-${genre_index}`} className="self-start py-1 px-2 rounded-sm bg-gray-200">{genre_name}</div>
                ))
            }</div>
        </div>
    );
}
