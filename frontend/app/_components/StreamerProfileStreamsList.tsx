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

export function StreamerProfileStreamsList({ streams }: { streams: TwitchStream[] }) {
    const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
    const visibleStreams = streams.slice(0, visibleCount);
    const hasMore = visibleCount < streams.length;

    return (
        <>
            {visibleStreams.map((stream, index) => (
                <div key={`stream-${stream.id}`}
                    className="relative border border-gray-300 mt-6 p-6 rounded-sm bg-white text-sm"
                >
                    <div className="absolute top-1 left-2 text-xs text-gray-500">#{index + 1}</div>
                    <StreamSnapshotsChart
                        snapshots={stream.snapshots}
                        started_at={stream.started_at}
                        games={stream.games}
                        host_game_ids={stream.host_game_ids}
                    />
                    <div><span className="text-brand-blue">Started: </span><span>{formatStreamTime(stream.started_at)}</span></div>
                    <div><span className="text-brand-blue">Finished: </span><span>{formatStreamTime(stream.finished_at)}</span></div>
                    <div><span className="text-brand-blue">Duration: </span><span>{stream.duration}</span></div>
                    <div><span className="text-brand-blue">Peak Viewers: </span><span>{stream.max_viewers}</span></div>
                    <div><span className="text-brand-blue">Language: </span><span>{stream.language}</span></div>
                </div>
            ))}
            {hasMore && (
                <div className="pt-6 text-center">
                    <button
                        type="button"
                        onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                        className="inline-block py-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer"
                    >
                        Show More
                    </button>
                </div>
            )}
        </>
    );
}
