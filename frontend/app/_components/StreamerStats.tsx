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
};

// As on a profile's chart: today and the 27 days before it, newest first.
const STRIP_DAYS = 28;
// The site's charts' first blue, on the grey of an empty day.
const STREAMED_COLOR = "#0072B2";
const EMPTY_COLOR = "#e5e7eb";

// Fills the width it's given, with a wider gap between the weeks, so a weekly rhythm reads
// without counting.
function DayStrip({ days_ago }: { days_ago: number[] }) {
    const streamed = new Set(days_ago);

    return (
        <div
            role="img"
            aria-label={`Streamed on ${days_ago.length} of the last ${STRIP_DAYS} days`}
            className="flex gap-0.5 mt-1"
        >
            {Array.from({ length: STRIP_DAYS }, (_, day) => (
                <span
                    key={day}
                    className={`flex-1 h-4 rounded-[1px] ${day > 0 && day % 7 === 0 ? "ml-1" : ""}`}
                    style={{ backgroundColor: streamed.has(day) ? STREAMED_COLOR : EMPTY_COLOR }}
                />
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
                        <div className="py-1 md:pr-4">
                            <span className="text-brand-blue uppercase">Days streamed: </span>
                            <span>{stats.days_ago.length} of the last {STRIP_DAYS}</span>
                            <DayStrip days_ago={stats.days_ago} />
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
