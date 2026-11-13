"use client";

import { useState, type CSSProperties, type ReactNode } from "react";

import { PagePicker, Pagination } from "../../_components/Pagination";
import type { Paging } from "../../_lib/paging";
import { GameHoursChart } from "./GameHoursChart";
import type { GameLanguage, GameListLabels, GameRow } from "./types";

// The same columns for the headings and the rows, so the numbers line up under their hour.
// On a phone a row takes two lines, the game's name over its numbers, or the name gets
// too narrow to read. The first column is as wide as the page's widest row number, in
// digits (--number-column). Each grid reads ch from its own font size, so the heading row
// keeps the rows' size and only its text is small.
const COLUMNS = "grid grid-cols-[var(--number-column)_repeat(3,minmax(0,1fr))_1rem] md:grid-cols-[var(--number-column)_minmax(0,1fr)_repeat(3,3.5rem)_1rem] gap-x-2";
// A number's column on a phone, by how old its hour is; from md up they just follow on.
const NUMBER_COLUMNS = ["col-start-2", "col-start-3", "col-start-4"];

const hourLabel = (hour: number) => `${String(hour % 24).padStart(2, "0")}:00`;

// How long a chart takes to slide open or shut, and a row to glide to the top of the screen;
// Slide's duration-300 is the same.
const SLIDE_MS = 300;
// The space left above a row brought to the top of the screen.
const ROW_TOP_GAP = 8;

/**
 * Brings a row just opened to the top of the screen, with its chart under it. A chart sliding
 * shut above it pulls it up meanwhile, so each frame reads where the row is and scrolls it to
 * where it should be by then: it glides from where it was clicked to the top, whichever way the
 * page moves under it. Scrolling by hand stops it.
 */
function bringToTop(row: HTMLElement, still: boolean) {
    if (still) {
        requestAnimationFrame(() => window.scrollBy(0, row.getBoundingClientRect().top - ROW_TOP_GAP));
        return;
    }
    const from = row.getBoundingClientRect().top;
    let stopped = false;
    const stop = () => {
        stopped = true;
    };
    const inputs = ["wheel", "touchstart", "keydown"] as const;
    inputs.forEach((name) => window.addEventListener(name, stop, { once: true, passive: true }));
    const start = performance.now();
    const step = (now: number) => {
        if (!stopped) {
            const progress = Math.min(1, (now - start) / SLIDE_MS);
            const eased = 1 - (1 - progress) ** 3;
            window.scrollBy(0, row.getBoundingClientRect().top - (from + (ROW_TOP_GAP - from) * eased));
        }
        // A little past the slide, so the row stays put while a chart above finishes shutting.
        if (!stopped && now - start < SLIDE_MS + 100) {
            requestAnimationFrame(step);
        } else {
            inputs.forEach((name) => window.removeEventListener(name, stop));
        }
    };
    requestAnimationFrame(step);
}

/**
 * Slides its content open or shut, by taking a grid row from none of its height to all of it.
 * Content opened by a click slides open; content open from the start just shows, so the page
 * doesn't shift while it loads. Once it has slid shut, `onShut` lets the row drop it.
 */
function Slide({ open, slideIn, onShut, children }: {
    open: boolean;
    slideIn: boolean;
    onShut: () => void;
    children: ReactNode;
}) {
    // Where it came to rest, open or shut, or null while it moves. It's clipped unless at rest
    // open, so its content can't spill over the rows below, and a focus ring at its edge shows
    // whole once it's open.
    const [rest, setRest] = useState<boolean | null>(slideIn ? null : open);
    const [lastOpen, setLastOpen] = useState(open);
    if (open !== lastOpen) {
        // Turned the other way: it moves again until the slide ends.
        setLastOpen(open);
        setRest(null);
    }
    return (
        <div
            className={`grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"} ${slideIn ? "starting:grid-rows-[0fr]" : ""}`}
            onTransitionEnd={(event) => {
                // The chart's own transitions end here too.
                if (event.target !== event.currentTarget || event.propertyName !== "grid-template-rows") return;
                setRest(open);
                if (!open) onShut();
            }}
        >
            <div className={`min-h-0 ${rest === true ? "" : "overflow-hidden"}`}>{children}</div>
        </div>
    );
}

/**
 * One page of the games in the list's stored order, each with its newest hours. A row opens
 * that game's chart under it; the top game's starts open, to show what a row holds. The chart's
 * language stays as picked from one game to the next, and from page to page. The other pages'
 * addresses are `path` with the filters in `query`.
 */
export function GamesList({ results, total, paging, newest_hour, path, query, peak, languages, default_language, labels }: {
    results: GameRow[];
    total: number;
    paging: Paging;
    newest_hour: number | null;
    path: string;
    query: string;
    peak: string;
    languages: GameLanguage[];
    default_language: string;
    labels: GameListLabels;
}) {
    const [openGame, setOpenGame] = useState<number | null>(results[0]?.id ?? null);
    // Charts sliding shut; each stays drawn until it has.
    const [shutting, setShutting] = useState<number[]>([]);
    // Charts slide once someone opens one; the top game's, open from the start, just shows.
    const [sliding, setSliding] = useState(false);
    const [chartLanguage, setChartLanguage] = useState(default_language);
    // Each row's number is its place in the list, so page 2's first is 51, and a game found by
    // name keeps its own. Rows from an older API, without a place, are numbered down the list.
    // The widest sets the column: 2 digits on page 1, 5 deep in the list.
    const firstNumber = (paging.page - 1) * paging.page_size + 1;
    const placeOf = (game: GameRow, index: number) => game.place ?? firstNumber + index;
    const numberDigits = String(results.reduce((widest, game, index) => Math.max(widest, placeOf(game, index)), 1)).length;

    // Opens a game's chart, shutting the open one, or shuts the chart if it's the open one. An
    // opened row goes to the top of the screen: a chart shutting above it would pull it up, off
    // the screen on a phone, where a chart is taller than it.
    function toggleGame(gameId: number, row: HTMLElement) {
        const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        // The open chart slides shut; with motion reduced it just goes.
        const shut = openGame !== null && !still ? [openGame] : [];
        setShutting((ids) => [...ids.filter((id) => id !== gameId && !shut.includes(id)), ...shut]);
        setSliding(!still);
        if (openGame === gameId) {
            setOpenGame(null);
            return;
        }
        setOpenGame(gameId);
        bringToTop(row, still);
    }

    if (newest_hour === null) {
        return <p>{labels.no_data}</p>;
    }
    if (results.length === 0) {
        return <p>{labels.no_results}</p>;
    }

    return (
        <div style={{ "--number-column": `${numberDigits}ch` } as CSSProperties}>
            {/* The page dropdown under the count, so another page is a pick away without going
                down to the end of this one. */}
            <div className="mb-8 flex flex-col items-start gap-3">
                <div className="text-lg text-brand-blue">
                    {total === 1 ? labels.found_count_one : labels.found_count.replace("{count}", total.toLocaleString())}
                </div>
                <PagePicker
                    path={path}
                    query={query}
                    page={paging.page}
                    pages={paging.pages}
                    labels={labels.pagination}
                    className="text-sm"
                />
            </div>

            <div className="text-xs text-gray-600 text-right pr-6 pb-1">{labels.hours_caption}</div>
            <div className={`${COLUMNS} text-gray-600 px-1.5 pb-1 border-b border-b-gray-400`} aria-hidden="true">
                <span className="hidden md:block text-xs">#</span>
                <span className="hidden md:block text-xs">{labels.game_column}</span>
                {[0, 1, 2].map((age) => (
                    <span key={age} className={`${NUMBER_COLUMNS[age]} md:col-start-auto text-xs text-right tabular-nums`}>
                        {hourLabel(newest_hour - age)}
                    </span>
                ))}
                <span className="hidden md:block" />
            </div>

            <ol>
                {results.map((game, index) => {
                    const open = openGame === game.id;
                    const about = [game.genres.join(", "), game.release_year].filter(Boolean).join(" · ");
                    return (
                        <li key={game.id} className="border-b border-b-gray-300">
                            <button
                                type="button"
                                aria-expanded={open}
                                onClick={(event) => toggleGame(game.id, event.currentTarget)}
                                className={`${COLUMNS} w-full items-baseline text-left px-1.5 py-2 cursor-pointer hover:bg-gray-100 aria-expanded:bg-gray-100`}
                            >
                                <span className="text-gray-500 tabular-nums">{placeOf(game, index)}</span>
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
                            {(open || shutting.includes(game.id)) && (
                                <Slide
                                    open={open}
                                    slideIn={sliding}
                                    onShut={() => setShutting((ids) => ids.filter((id) => id !== game.id))}
                                >
                                    <GameHoursChart
                                        key={`${game.id}|${peak}`}
                                        gameId={game.id}
                                        peak={peak}
                                        languages={languages}
                                        language={chartLanguage}
                                        onLanguageChange={setChartLanguage}
                                        labels={labels.chart}
                                    />
                                </Slide>
                            )}
                        </li>
                    );
                })}
            </ol>

            {paging.pages > 1 && (
                <div className="mt-12">
                    <Pagination path={path} query={query} page={paging.page} pages={paging.pages} labels={labels.pagination} />
                </div>
            )}
        </div>
    );
}
