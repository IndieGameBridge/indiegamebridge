export type StreamerStatsData = {
    peak_viewers: number;
    avg_viewers: number;
    streams_count: number;
    hours_streamed: number;
    genres: string[];
};

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
