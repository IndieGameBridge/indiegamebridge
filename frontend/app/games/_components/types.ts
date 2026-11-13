import type { PaginationLabels } from "../../_components/Pagination";
import type { Paging } from "../../_lib/paging";

export type GameFilter = {
    name: string;
    label: string;
    values: { v: string | number; l: string }[];
    default: string | number;
    // The name box is typed into rather than picked from, so its values are empty.
    type?: "text";
    placeholder?: string;
    max_length?: number;
};

export type GameRow = {
    id: number;
    // Its number in the list the filters make, the name left out: a game found by name
    // keeps the number it has in the list. Absent from an API older than the name search.
    place?: number;
    name: string;
    release_year: number | null;
    genres: string[];
    // The newest hours' streams, newest first.
    recent_streams: number[];
};

export type GameSearchResponse = Paging & {
    results: GameRow[];
    total: number;
    // Whole hours since the Unix epoch; null until the stats have first been built.
    newest_hour: number | null;
};

export type GameHoursResponse = {
    newest_hour: number | null;
    window_hours: number;
    // Per language, the hours with streams and their streams, newest first.
    lines: Record<string, { hours: number[]; streams: number[] }>;
};

export type GameLanguage = {
    code: string;
    label: string;
    // The hour collecting began, for a language whose 4 weeks haven't filled yet.
    since_hour: number | null;
};

export type GameChartLabels = {
    language: string;
    all_languages: string;
    loading: string;
    error: string;
    empty: string;
    caption: string;
    caption_all: string;
    utc: string;
    your_time: string;
    your_time_long: string;
};

export type GameListLabels = {
    found_count: string;
    found_count_one: string;
    no_results: string;
    no_data: string;
    game_column: string;
    hours_caption: string;
    pagination: PaginationLabels;
    chart: GameChartLabels;
};
