export type GameFilter = {
    name: string;
    label: string;
    values: { v: string | number; l: string }[];
    default: string | number;
};

export type GameRow = {
    id: number;
    name: string;
    release_year: number | null;
    genres: string[];
    // The newest hours' streams, newest first.
    recent_streams: number[];
};

export type GameSearchResponse = {
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
    show_more: string;
    loading: string;
    chart: GameChartLabels;
};
