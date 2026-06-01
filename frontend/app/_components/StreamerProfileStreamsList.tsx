"use client";

import { useState } from "react";

import { formatStreamTime } from "../_lib/format";
import { StreamSnapshotsChart } from "./StreamSnapshotsChart";

type Snapshot = {
    g: number;
    t: number;
    v: number;
};

export type TwitchStream = {
    id: number;
    games: string[];
    host_game_ids: number[];
    duration: string;
    language: string;
    snapshots: Snapshot[];
    started_at: string;
    finished_at: string;
    max_viewers: number;
};

const PAGE_SIZE = 20;

export function StreamerProfileStreamsList({ streams, showMoreLabel }: { streams: TwitchStream[]; showMoreLabel: string }) {
    const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
    const visibleStreams = streams.slice(0, visibleCount);
    const hasMore = visibleCount < streams.length;

    return (
        <>
            {visibleStreams.map((stream, index) => {
                const avgViewers = stream.snapshots.length > 0
                    ? Math.round(stream.snapshots.reduce((sum, s) => sum + s.v, 0) / stream.snapshots.length)
                    : 0;
                return (
                <div key={`stream-${stream.id}`}
                    className="relative border-t border-t-gray-400 mb-24 pt-8 bg-white text-sm"
                >
                    <div className="absolute top-2 left-2 text-xs text-gray-500">#{index + 1}</div>
                    <StreamSnapshotsChart
                        snapshots={stream.snapshots}
                        started_at={stream.started_at}
                        games={stream.games}
                        host_game_ids={stream.host_game_ids}
                    />
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
                        <div>
                            <div className="p-1"><span className="text-brand-blue">Peak Viewers: </span><span>{stream.max_viewers}</span></div>
                            <div className="p-1"><span className="text-brand-blue">Avg Viewers: </span><span>{avgViewers}</span></div>
                            <div className="p-1"><span className="text-brand-blue">Duration: </span><span>{stream.duration}</span></div>
                        </div>
                        <div>
                            <div className="p-1"><span className="text-brand-blue">Started: </span><span>{formatStreamTime(stream.started_at)} UTC</span></div>
                            <div className="p-1"><span className="text-brand-blue">Finished: </span><span>{formatStreamTime(stream.finished_at)} UTC</span></div>
                            <div className="p-1"><span className="text-brand-blue">Language: </span><span>{stream.language}</span></div>
                        </div>
                    </div>
                </div>
                );
            })}
            {hasMore && (
                <div className="text-center mb-24">
                    <button
                        type="button"
                        onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
                    >
                        {showMoreLabel}
                    </button>
                </div>
            )}
        </>
    );
}
