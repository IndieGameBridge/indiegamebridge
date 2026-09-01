import { PROFILE_SERIES } from "./StreamerActivityChart";
import { ProfileBarChart } from "./ProfileBarChart";

export type StreamerGenreActivity = {
    x: string;
    hours: number;
    peak: number;
    avg: number;
};

export function StreamerGenreChart({ genres }: { genres: StreamerGenreActivity[] }) {
    return (
        <ProfileBarChart
            title="Hours and viewers per genre"
            caption="Hours streamed and viewers per genre over the last 4 weeks"
            description={
                "Horizontal bar chart with one group per game genre over the last 4 weeks," +
                " most-streamed genre first, showing hours streamed, peak viewers and average" +
                " viewers. Each series is scaled to its own maximum."
            }
            rowHeader="Genre"
            series={PROFILE_SERIES}
            rows={genres.map((genre) => ({
                label: genre.x,
                values: { hours: genre.hours, peak: genre.peak, avg: genre.avg },
            }))}
            note={
                "A game counts toward every genre it carries, so genres overlap and the hours" +
                " add up to more than the total hours streamed."
            }
        />
    );
}
