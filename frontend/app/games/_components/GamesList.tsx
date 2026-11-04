"use client";

import { useState } from "react";

import { loadGamesPage } from "../actions";
import { GameHoursChart } from "./GameHoursChart";
import type { GameLanguage, GameListLabels, GameRow } from "./types";

// The same columns for the headings and the rows, so the numbers line up under their hour.
// On a phone a row takes two lines, the game's name over its numbers, or the name gets
// too narrow to read.
const COLUMNS = "grid grid-cols-[2rem_repeat(3,minmax(0,1fr))_1rem] md:grid-cols-[2.25rem_minmax(0,1fr)_repeat(3,3.5rem)_1rem] gap-x-2";
// A number's column on a phone, by how old its hour is; from md up they just follow on.
const NUMBER_COLUMNS = ["col-start-2", "col-start-3", "col-start-4"];

const hourLabel = (hour: number) => `${String(hour % 24).padStart(2, "0")}:00`;

/**
 * The games in the list's stored order, each with its newest hours. A row opens that
 * game's chart under it; the top game's starts open, to show what a row holds. The chart's
 * language stays as picked from one game to the next.
 */
export function GamesList({ results, total, newest_hour, api_query, peak, languages, default_language, labels }: {
    results: GameRow[];
    total: number;
    newest_hour: number | null;
    api_query: string;
    peak: string;
    languages: GameLanguage[];
    default_language: string;
    labels: GameListLabels;
}) {
    const [games, setGames] = useState(results);
    const [knownTotal, setKnownTotal] = useState(total);
    const [loadedPage, setLoadedPage] = useState(1);
    const [loading, setLoading] = useState(false);
    const [openGame, setOpenGame] = useState<number | null>(results[0]?.id ?? null);
    const [chartLanguage, setChartLanguage] = useState(default_language);

    async function handleShowMore() {
        if (loading) return;
        const nextPage = loadedPage + 1;
        setLoading(true);
        try {
            const data = await loadGamesPage(api_query, nextPage);
            setGames((previous) => [...previous, ...data.results]);
            setKnownTotal(data.total);
            setLoadedPage(nextPage);
        } finally {
            setLoading(false);
        }
    }

    if (newest_hour === null) {
        return <p>{labels.no_data}</p>;
    }
    if (games.length === 0) {
        return <p>{labels.no_results}</p>;
    }

    return (
        <div>
            <div className="mb-8 text-lg text-brand-blue">
                {knownTotal === 1 ? labels.found_count_one : labels.found_count.replace("{count}", knownTotal.toLocaleString())}
            </div>

            <div className="text-xs text-gray-600 text-right pr-6 pb-1">{labels.hours_caption}</div>
            <div className={`${COLUMNS} text-xs text-gray-600 px-1.5 pb-1 border-b border-b-gray-400`} aria-hidden="true">
                <span className="hidden md:block">#</span>
                <span className="hidden md:block">{labels.game_column}</span>
                {[0, 1, 2].map((age) => (
                    <span key={age} className={`${NUMBER_COLUMNS[age]} md:col-start-auto text-right tabular-nums`}>
                        {hourLabel(newest_hour - age)}
                    </span>
                ))}
                <span className="hidden md:block" />
            </div>

            <ol>
                {games.map((game, index) => {
                    const open = openGame === game.id;
                    const about = [game.genres.join(", "), game.release_year].filter(Boolean).join(" · ");
                    return (
                        <li key={game.id} className="border-b border-b-gray-300">
                            <button
                                type="button"
                                aria-expanded={open}
                                onClick={() => setOpenGame(open ? null : game.id)}
                                className={`${COLUMNS} w-full items-baseline text-left px-1.5 py-2 cursor-pointer hover:bg-gray-100 aria-expanded:bg-gray-100`}
                            >
                                <span className="text-gray-500 tabular-nums">{index + 1}</span>
                                <span className="min-w-0 col-span-3 md:col-span-1 wrap-anywhere">
                                    <span className="font-bold">{game.name}</span>
                                    {about && <span className="block text-xs text-gray-600">{about}</span>}
                                </span>
                                {game.recent_streams.map((streams, age) => (
                                    <span
                                        key={age}
                                        className={`${NUMBER_COLUMNS[age]} row-start-2 md:col-start-auto md:row-start-auto text-right tabular-nums ${age === 0 ? "font-bold" : "text-gray-600"}`}
                                    >
                                        {streams.toLocaleString("en-US")}
                                    </span>
                                ))}
                                <span className="col-start-5 row-start-1 md:col-start-auto md:row-start-auto text-gray-500 text-right" aria-hidden="true">
                                    {open ? "▴" : "▾"}
                                </span>
                            </button>
                            {open && (
                                <GameHoursChart
                                    key={`${game.id}|${peak}`}
                                    gameId={game.id}
                                    peak={peak}
                                    languages={languages}
                                    language={chartLanguage}
                                    onLanguageChange={setChartLanguage}
                                    labels={labels.chart}
                                />
                            )}
                        </li>
                    );
                })}
            </ol>

            {games.length < knownTotal && (
                <div className="text-center mt-12">
                    <button
                        type="button"
                        onClick={handleShowMore}
                        disabled={loading}
                        className="text-sm inline-block p-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 min-w-36 border border-blue-600 hover:border-blue-700 cursor-pointer disabled:bg-gray-400 disabled:border-gray-400 disabled:hover:bg-gray-400 disabled:hover:border-gray-400 disabled:cursor-not-allowed"
                    >
                        {labels.show_more}
                    </button>
                    {loading && <div className="pt-2 text-sm text-gray-600">{labels.loading}</div>}
                </div>
            )}
        </div>
    );
}
