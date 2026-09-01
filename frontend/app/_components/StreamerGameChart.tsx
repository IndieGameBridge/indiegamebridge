import { PROFILE_SERIES } from "./StreamerActivityChart";
import { GroupedBarChart, GroupedBarSeries } from "./GroupedBarChart";

export type StreamerGameActivity = {
    name: string;
    genres: string[];
    hours: number;
    streams: number;
    maxv: number;
    avgv: number;
};

// Reddish purple, from the same Okabe-Ito palette as the three shared series and
// distinct from all of them. Only this chart counts streams, so it isn't shared.
const STREAMS_SERIES: GroupedBarSeries = {
    key: "streams",
    label: "Streams",
    color: "#ce0c78",
    format: (v) => v.toLocaleString(),
};

const GAME_SERIES: GroupedBarSeries[] = [...PROFILE_SERIES, STREAMS_SERIES];

export function StreamerGameChart({ games }: { games: StreamerGameActivity[] }) {
    return (
        <GroupedBarChart
            title="Hours, viewers and streams per game"
            caption="Hours streamed, viewers and streams per game over the last 4 weeks"
            description={
                "Horizontal bar chart with one group per game over the last 4 weeks," +
                " most-played game first, showing hours streamed, peak viewers, average" +
                " viewers and number of streams, with the game's genres underneath. Each" +
                " series is scaled to its own maximum."
            }
            rowHeader="Game"
            series={GAME_SERIES}
            rows={games.map((game) => ({
                label: game.name,
                subLabel: game.genres.join(" • "),
                values: {
                    hours: game.hours,
                    peak: game.maxv,
                    avg: game.avgv,
                    streams: game.streams,
                },
            }))}
            note={
                "A stream's time is split across the games it played, so the hours add up to" +
                " the total hours streamed. A stream counts once for every game it played."
            }
        />
    );
}
