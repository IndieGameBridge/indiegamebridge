"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { loadGameHours } from "../actions";
import type { GameChartLabels, GameHoursResponse, GameLanguage } from "./types";

// A colour per language, the same on every game's chart.
const LANGUAGE_COLORS: Record<string, string> = {
    en: "#0072B2",
    fr: "#D55E00",
    de: "#8C6BB1",
    es: "#009E73",
    pt: "#E69F00",
    ja: "#CC79A7",
    it: "#56B4E9",
    zh: "#A5632E",
};

// One hour's width: every hour keeps its own label and number, so the chart is long and
// scrolls sideways. It opens on the newest hour, on the left.
const HOUR_WIDTH = 36;
const EDGE = 20;
const HEIGHT = 372;
const TOP = 24;
const LABEL_ROW = 17;
const AXIS_WIDTH = 52;
const TIP_WIDTH = 248;

const WEEKEND_COLOR = "#eef3f6";
const GRID_COLOR = "#e5e7eb";
const MUTED_COLOR = "#6b7280";

const utcDay = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" });
const localClock = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

const toDate = (hour: number) => new Date(hour * 3600000);
const twoDigits = (value: number) => String(value).padStart(2, "0");
const utcClock = (hour: number) => `${twoDigits(hour % 24)}:00`;
const dayLabel = (hour: number) => utcDay.format(toDate(hour)).replace(",", "");
const formatCount = (value: number) => value.toLocaleString("en-US");
// The viewer's hour, with its minutes only in a zone that isn't on the hour.
const localHourLabel = (hour: number) => localClock.format(toDate(hour)).replace(":00", "");
const xOf = (age: number) => EDGE + age * HOUR_WIDTH;

type Series = {
    code: string;
    label: string;
    // Streams by age: 0 is the newest hour.
    values: number[];
    // The oldest age the language has been collected for.
    oldestAge: number;
};

function niceScale(max: number) {
    const rough = Math.max(max, 1) / 4;
    const power = 10 ** Math.floor(Math.log10(rough));
    const unit = Math.max(1, [1, 2, 2.5, 5, 10].find((step) => step * power >= rough)! * power);
    return { unit, top: Math.ceil(Math.max(max, 1) / unit) * unit };
}

function seriesOf(data: GameHoursResponse, languages: GameLanguage[], language: string): Series[] {
    const newest = data.newest_hour;
    if (newest === null) return [];
    const series: Series[] = [];
    for (const one_language of languages) {
        const line = data.lines[one_language.code];
        if (!line || (language !== "all" && language !== one_language.code)) continue;
        const values = new Array<number>(data.window_hours).fill(0);
        line.hours.forEach((hour, index) => {
            const age = newest - hour;
            if (age >= 0 && age < values.length) values[age] = line.streams[index];
        });
        const collected = one_language.since_hour === null ? values.length - 1 : newest - one_language.since_hour;
        series.push({
            code: one_language.code,
            label: one_language.label,
            values,
            oldestAge: Math.max(0, Math.min(values.length - 1, collected)),
        });
    }
    return series;
}

function Drawing({ series, newest, windowHours, axis, yOf, ticks, labelRows, showLocal }: {
    series: Series[];
    newest: number;
    windowHours: number;
    axis: number;
    yOf: (value: number) => number;
    ticks: number[];
    labelRows: number;
    showLocal: boolean;
}) {
    const ages = Array.from({ length: windowHours }, (_, age) => age);
    const width = EDGE * 2 + HOUR_WIDTH * (windowHours - 1);
    const rowY = (row: number) => axis + 16 + row * LABEL_ROW;
    const isWeekend = (age: number) => [0, 6].includes(toDate(newest - age).getUTCDay());
    const weekendStarts = ages.filter((age) => isWeekend(age) && (age === 0 || !isWeekend(age - 1)));
    const single = series.length === 1;
    return (
        <g>
            {weekendStarts.map((start) => {
                let end = start;
                while (end + 1 < windowHours && isWeekend(end + 1)) end += 1;
                return (
                    <rect
                        key={start}
                        x={xOf(start) - HOUR_WIDTH / 2}
                        y={TOP}
                        width={(end - start + 1) * HOUR_WIDTH}
                        height={axis - TOP}
                        fill={WEEKEND_COLOR}
                    />
                );
            })}
            {ticks.map((tick) => (
                <line key={tick} x1={0} x2={width} y1={yOf(tick)} y2={yOf(tick)} stroke={GRID_COLOR} />
            ))}
            {ages.map((age) => {
                const hour = newest - age;
                const x = xOf(age);
                const hourOfDay = hour % 24;
                return (
                    <g key={age} fontSize="12" className="fill-gray-600">
                        {/* A day's first hour: the day before starts to its right. */}
                        {hourOfDay === 0 && (
                            <line x1={x + HOUR_WIDTH / 2} x2={x + HOUR_WIDTH / 2} y1={TOP} y2={HEIGHT} stroke={MUTED_COLOR} strokeOpacity={0.45} />
                        )}
                        <text x={x} y={rowY(0)} textAnchor="middle">{twoDigits(hourOfDay)}</text>
                        {showLocal && <text x={x} y={rowY(1)} textAnchor="middle">{localHourLabel(hour)}</text>}
                        {/* Every 6 hours, so a phone always has a date on screen. */}
                        {hourOfDay % 6 === 3 && age > 0 && (
                            <text x={x} y={rowY(labelRows - 1)} textAnchor="middle" className="fill-gray-900">{dayLabel(hour)}</text>
                        )}
                    </g>
                );
            })}
            {series.map((one) => {
                const color = LANGUAGE_COLORS[one.code];
                const shown = one.values.slice(0, one.oldestAge + 1);
                return (
                    <g key={one.code}>
                        <polyline
                            points={shown.map((value, age) => `${xOf(age)},${yOf(value).toFixed(1)}`).join(" ")}
                            fill="none"
                            stroke={color}
                            strokeWidth={2}
                            strokeLinejoin="round"
                            strokeLinecap="round"
                        />
                        {single && shown.map((value, age) => (
                            <g key={age}>
                                <circle cx={xOf(age)} cy={yOf(value)} r={2.5} fill={color} />
                                <text
                                    x={xOf(age)}
                                    y={yOf(value) - 8}
                                    textAnchor="middle"
                                    fontSize="11"
                                    stroke="#ffffff"
                                    strokeWidth={3}
                                    paintOrder="stroke"
                                    className={value ? "fill-gray-900" : "fill-gray-400"}
                                >
                                    {formatCount(value)}
                                </text>
                            </g>
                        ))}
                        <circle cx={xOf(0)} cy={yOf(shown[0])} r={4} fill={color} stroke="#ffffff" strokeWidth={2} />
                    </g>
                );
            })}
        </g>
    );
}

/**
 * One game's streams in each hour of the last 4 weeks, a line per language, on one long
 * timeline: the newest hour on the left, older hours further right. With one language
 * picked, every hour shows its number. The left axis stays put while the hours scroll.
 */
export function GameHoursChart({ gameId, peak, languages, language, onLanguageChange, labels }: {
    gameId: number;
    peak: string;
    languages: GameLanguage[];
    language: string;
    onLanguageChange: (language: string) => void;
    labels: GameChartLabels;
}) {
    const [data, setData] = useState<GameHoursResponse | null>(null);
    const [failed, setFailed] = useState(false);
    const [cursor, setCursor] = useState<{ age: number; tipLeft: number } | null>(null);
    const chartRef = useRef<HTMLDivElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const hoursRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        let cancelled = false;
        loadGameHours(gameId, peak)
            .then((response) => { if (!cancelled) setData(response); })
            .catch(() => { if (!cancelled) setFailed(true); });
        return () => { cancelled = true; };
    }, [gameId, peak]);

    const series = useMemo(() => (data ? seriesOf(data, languages, language) : []), [data, languages, language]);

    const scale = useMemo(() => {
        if (series.length === 0) return null;
        const showLocal = Intl.DateTimeFormat().resolvedOptions().timeZone !== "UTC";
        const labelRows = showLocal ? 3 : 2;
        const axis = HEIGHT - labelRows * LABEL_ROW - 10;
        const { unit, top } = niceScale(Math.max(...series.flatMap((one) => one.values.slice(0, one.oldestAge + 1))));
        const yOf = (value: number) => TOP + (axis - TOP) * (1 - value / top);
        const ticks = Array.from({ length: Math.round(top / unit) + 1 }, (_, index) => index * unit);
        return { showLocal, labelRows, axis, yOf, ticks };
    }, [series]);

    const windowHours = data?.window_hours ?? 0;
    const newest = data?.newest_hour ?? null;
    const width = EDGE * 2 + HOUR_WIDTH * Math.max(windowHours - 1, 0);

    const drawing = useMemo(() => {
        if (!scale || newest === null) return null;
        return <Drawing series={series} newest={newest} windowHours={windowHours} {...scale} />;
    }, [scale, series, newest, windowHours]);

    // Puts the cursor on an hour, with its box beside the pointer, or beside the hour when
    // the keyboard moved it, and on the other side where it would leave the chart.
    function moveCursor(age: number, pointerX?: number) {
        const chart = chartRef.current!.getBoundingClientRect();
        const anchor = pointerX ?? hoursRef.current!.getBoundingClientRect().left + xOf(age);
        const left = anchor - chart.left + 14;
        setCursor({ age, tipLeft: left + TIP_WIDTH > chart.width ? Math.max(0, left - TIP_WIDTH - 28) : left });
    }

    function handlePointer(event: React.PointerEvent) {
        const box = hoursRef.current!.getBoundingClientRect();
        const age = Math.round((event.clientX - box.left - EDGE) / HOUR_WIDTH);
        moveCursor(Math.min(windowHours - 1, Math.max(0, age)), event.clientX);
    }

    function handleKey(event: React.KeyboardEvent) {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        // Newer hours are to the left.
        const step = event.key === "ArrowLeft" ? -1 : 1;
        const age = Math.min(windowHours - 1, Math.max(0, cursor === null ? 0 : cursor.age + step));
        const scroller = scrollRef.current!;
        const x = xOf(age);
        if (x < scroller.scrollLeft + 24 || x > scroller.scrollLeft + scroller.clientWidth - 24) {
            scroller.scrollLeft = x - scroller.clientWidth / 2;
        }
        moveCursor(age);
    }

    const tip = useMemo(() => {
        if (cursor === null || newest === null) return null;
        const hour = newest - cursor.age;
        const rows = series
            .filter((one) => cursor.age <= one.oldestAge)
            .map((one) => ({ code: one.code, label: one.label, value: one.values[cursor.age] }))
            .sort((first, second) => second.value - first.value);
        return { hour, rows, left: cursor.tipLeft };
    }, [cursor, newest, series]);

    const buttonClass = (active: boolean) => active
        ? "py-0.5 px-2 rounded border border-brand-blue bg-brand-blue text-white text-xs cursor-pointer"
        : "py-0.5 px-2 rounded border border-gray-300 hover:border-brand-blue text-xs cursor-pointer";

    return (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-y-3 pt-3 pb-6">
            <div role="group" aria-label={labels.language} className="flex flex-row flex-wrap gap-1.5">
                {[{ code: "all", label: labels.all_languages }, ...languages].map((one) => (
                    <button
                        key={one.code}
                        type="button"
                        aria-pressed={language === one.code}
                        className={buttonClass(language === one.code)}
                        onClick={() => onLanguageChange(one.code)}
                    >
                        {one.label}
                    </button>
                ))}
            </div>

            {failed && <p className="text-sm text-gray-600 py-6">{labels.error}</p>}
            {!failed && !data && <p className="text-sm text-gray-600 py-6">{labels.loading}</p>}
            {data && series.length === 0 && <p className="text-sm text-gray-600 py-6">{labels.empty}</p>}

            {scale && drawing && (
                <div>
                    {series.length > 1 && (
                        <div className="flex flex-row flex-wrap gap-x-3.5 gap-y-1 text-xs mb-1">
                            {series.map((one) => (
                                <span key={one.code} className="inline-flex items-center gap-1.5">
                                    <i className="inline-block w-3.5 h-0.75 rounded-sm" style={{ background: LANGUAGE_COLORS[one.code] }} />
                                    {one.label}
                                </span>
                            ))}
                        </div>
                    )}
                    <div ref={chartRef} className="relative">
                        <div className="grid grid-cols-[52px_minmax(0,1fr)]">
                            <svg width={AXIS_WIDTH} height={HEIGHT} aria-hidden="true" className="block">
                                <g fontSize="12" className="fill-gray-600">
                                    {scale.ticks.map((tick) => (
                                        <text key={tick} x={AXIS_WIDTH - 8} y={scale.yOf(tick) + 4} textAnchor="end">{formatCount(tick)}</text>
                                    ))}
                                    <text x={AXIS_WIDTH - 8} y={scale.axis + 16} textAnchor="end">{labels.utc}</text>
                                    {scale.showLocal && (
                                        <text x={AXIS_WIDTH - 8} y={scale.axis + 16 + LABEL_ROW} textAnchor="end">{labels.your_time}</text>
                                    )}
                                </g>
                            </svg>
                            <div ref={scrollRef} className="overflow-x-auto">
                                <svg
                                    ref={hoursRef}
                                    width={width}
                                    height={HEIGHT}
                                    role="img"
                                    tabIndex={0}
                                    aria-label={labels.caption}
                                    className="block touch-pan-x outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue-600"
                                    onPointerMove={handlePointer}
                                    onPointerDown={handlePointer}
                                    onPointerLeave={() => setCursor(null)}
                                    onBlur={() => setCursor(null)}
                                    onKeyDown={handleKey}
                                >
                                    {drawing}
                                    {cursor !== null && (
                                        <g>
                                            <line x1={xOf(cursor.age)} x2={xOf(cursor.age)} y1={TOP} y2={scale.axis} stroke={MUTED_COLOR} />
                                            {series.filter((one) => cursor.age <= one.oldestAge).map((one) => (
                                                <circle
                                                    key={one.code}
                                                    cx={xOf(cursor.age)}
                                                    cy={scale.yOf(one.values[cursor.age])}
                                                    r={4}
                                                    fill={LANGUAGE_COLORS[one.code]}
                                                    stroke="#ffffff"
                                                    strokeWidth={2}
                                                />
                                            ))}
                                        </g>
                                    )}
                                </svg>
                            </div>
                        </div>
                        {tip && (
                            <div
                                className="absolute top-2 z-10 pointer-events-none bg-white border border-gray-200 rounded shadow-md px-2.5 py-1.5 text-xs"
                                style={{ left: tip.left, width: TIP_WIDTH }}
                            >
                                <div className="font-bold">{dayLabel(tip.hour)}, {utcClock(tip.hour)} to {utcClock(tip.hour + 1)} UTC</div>
                                {scale.showLocal && (
                                    <div className="text-gray-600 mb-1">
                                        {localClock.format(toDate(tip.hour))} to {localClock.format(toDate(tip.hour + 1))} {labels.your_time_long}
                                    </div>
                                )}
                                {tip.rows.map((row) => (
                                    <div key={row.code} className="flex flex-row justify-between gap-3 tabular-nums">
                                        <span>{row.label}</span>
                                        <span>{formatCount(row.value)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {scale && (
                <p className="text-xs text-gray-600">
                    {labels.caption}{series.length > 1 ? ` ${labels.caption_all}` : ""}
                </p>
            )}
        </div>
    );
}
