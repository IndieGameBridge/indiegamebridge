import { GroupedBarChart } from "./GroupedBarChart";
import { PROFILE_SERIES } from "./StreamerActivityChart";

export type StreamerWindowActivity = {
    code: string;
    // Where it's evening in this part of the day, e.g. "Europe & Africa".
    label: string;
    // e.g. "15:00–23:00 UTC".
    utc_hours: string;
    hours: number;
    // Percent of the streamer's time in the last 4 weeks.
    share: number;
};

/** How a streamer's last 4 weeks of streaming spread over the parts of the day, each named
 * after where it's evening then. */
export function StreamerWindowsChart({ windows }: { windows: StreamerWindowActivity[] }) {
    if (windows.every((window) => window.hours === 0)) return null;
    // The hours series' colour, as on the profile's other charts.
    const color = PROFILE_SERIES[0].color;
    return (
        <GroupedBarChart
            title="When they stream, by where it's evening"
            caption="Share of streaming time in each part of the day over the last 4 weeks"
            description={
                "Horizontal bar chart with one bar per part of the day, each named after where it's evening" +
                " then, showing the share of the streamer's streaming time in the last 4 weeks."
            }
            rowHeader="Evening in"
            series={[{ key: "share", label: "Share of streaming time", color, format: (v) => `${v}%`, legendSuffix: "" }]}
            rows={windows.map((window) => ({
                label: window.label,
                subLabel: window.utc_hours,
                values: { share: window.share },
                valueLabels: { share: `${window.share}% · ${window.hours} h` },
            }))}
            scale="shared"
            note={
                "Viewers mostly watch live in their own evening, so this shows which audience the streamer can" +
                " reach. It says when they go live, not where they live."
            }
        />
    );
}
