import { Fragment } from "react/jsx-runtime";
import { ProgressLink as Link } from "./ProgressLink";

import type { CurrentUser } from "../_lib/auth";
import type { StreamerData } from "./SearchStreamerResultsList";

type FeatureText = {
    title: string;
    text: string;
};

type GameRow = {
    id: number;
    name: string;
    // The newest hours' streams, newest first.
    recent_streams: number[];
};

type GenreRow = {
    name: string;
    streams: number;
    // Indie, so a reader finds it among the biggest genres.
    marked: boolean;
};

export type HomeShowcaseContent = {
    header_buttons: { streamers: string; games: string };
    streamers: FeatureText & {
        btn: string;
        sample_title: string;
        columns: { name: string; avg: string; streams: string; hours: string };
        rows: StreamerData[];
    };
    lists: FeatureText & { login_btn: string; open_btn: string };
    games: FeatureText & {
        btn: string;
        sample_title: string;
        columns: { name: string; hours: string[] };
        // Absent until the page's cached text is rebuilt with it.
        rows?: GameRow[];
    };
    genres: FeatureText & {
        btn: string;
        sample_title: string;
        rows: GenreRow[];
    };
};

// The blue the site's charts give their first series, and the orange that goes with it.
const BAR_COLOR = "#0072B2";
const MARKED_BAR_COLOR = "#E69F00";

const BUTTON = "text-sm inline-block py-2.25 px-6 text-white font-medium rounded border text-center";
const BLUE_BUTTON = `${BUTTON} bg-blue-600 border-blue-600 hover:bg-blue-700 hover:border-blue-700`;
const TWITCH_BUTTON = `${BUTTON} bg-twitch-brand border-twitch-brand hover:bg-twitch-brand-dark hover:border-twitch-brand-dark`;

// Tighter on a phone, where the headings wrap before the names do, and a very long name
// wraps too, so the columns fit without scrolling.
const NAME_HEADING = "w-full text-left font-bold py-2 pr-2 md:pr-4";
const NUMBER_HEADING = "text-right font-bold py-2 pl-2 md:pl-4 md:whitespace-nowrap";
const NAME_CELL = "text-left py-2 pr-2 md:pr-4 [overflow-wrap:anywhere]";
const NUMBER_CELL = "text-right py-2 pl-2 md:pl-4 tabular-nums";

/** The buttons in the home page's header: its two main ways in. */
export function HomeHeaderButtons({ labels }: { labels: HomeShowcaseContent["header_buttons"] }) {
    return (
        <Fragment>
            <Link href="/streamers" className={BLUE_BUTTON}>{labels.streamers}</Link>
            <Link href="/games" className={`${BUTTON} border-white hover:bg-white hover:text-brand-blue`}>{labels.games}</Link>
        </Fragment>
    );
}

function SampleTitle({ children }: { children: React.ReactNode }) {
    return <p className="mb-2 text-sm font-bold text-brand-blue">{children}</p>;
}

function StreamersSample({ content }: { content: HomeShowcaseContent["streamers"] }) {
    const { columns, rows, sample_title } = content;
    if (rows.length === 0) return null;
    return (
        <Fragment>
            <SampleTitle>{sample_title}</SampleTitle>
            <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr>
                        <th scope="col" className={NAME_HEADING}>{columns.name}</th>
                        <th scope="col" className={NUMBER_HEADING}>{columns.avg}</th>
                        <th scope="col" className={NUMBER_HEADING}>{columns.streams}</th>
                        <th scope="col" className={NUMBER_HEADING}>{columns.hours}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <tr key={row.profile_id} className="border-t border-gray-300">
                            <td className={NAME_CELL}>{row.display_name}</td>
                            <td className={NUMBER_CELL}>{row.avg_viewers.toLocaleString()}</td>
                            <td className={NUMBER_CELL}>{row.streams_count.toLocaleString()}</td>
                            <td className={NUMBER_CELL}>{row.hours_streamed.toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>
        </Fragment>
    );
}

function GamesSample({ content }: { content: HomeShowcaseContent["games"] }) {
    const { columns, rows = [], sample_title } = content;
    if (rows.length === 0) return null;
    return (
        <Fragment>
            <SampleTitle>{sample_title}</SampleTitle>
            <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr>
                        <th scope="col" className={NAME_HEADING}>{columns.name}</th>
                        {columns.hours.map((label) => (
                            <th key={label} scope="col" className={NUMBER_HEADING}>{label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((game) => (
                        <tr key={game.id} className="border-t border-gray-300">
                            <td className={NAME_CELL}>{game.name}</td>
                            {game.recent_streams.map((streams, age) => (
                                <td key={age} className={`${NUMBER_CELL} ${age === 0 ? "font-bold" : ""}`}>
                                    {streams.toLocaleString()}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            </div>
        </Fragment>
    );
}

function GenresSample({ content }: { content: HomeShowcaseContent["genres"] }) {
    const { rows, sample_title } = content;
    if (rows.length === 0) return null;
    const biggest = Math.max(...rows.map((row) => row.streams), 1);
    return (
        <Fragment>
            <SampleTitle>{sample_title}</SampleTitle>
            <table className="w-full border-collapse text-xs mt-3">
                <tbody>
                    {rows.map((row) => (
                        <tr key={row.name} className={row.marked ? "font-bold" : undefined}>
                            <th scope="row" className={`${row.marked ? "font-bold" : "font-normal"} text-right whitespace-nowrap py-1 pr-2.5`}>{row.name}</th>
                            <td className="w-full py-1">
                                <span
                                    aria-hidden="true"
                                    className="block h-4"
                                    style={{
                                        width: `${(row.streams / biggest) * 100}%`,
                                        backgroundColor: row.marked ? MARKED_BAR_COLOR : BAR_COLOR,
                                    }}
                                />
                            </td>
                            <td className="text-right tabular-nums py-1 pl-2.5">{row.streams.toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </Fragment>
    );
}

function Feature({ title, text, href, btn, border, children }: FeatureText & {
    href: string;
    btn: string;
    border?: boolean;
    children: React.ReactNode;
}) {
    return (
        <section className={`px-6 ${border ? "border-t border-gray-400" : ""}`}>
            <div className="max-w-[1000] mx-auto py-18 grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">
                <div className="min-w-0">
                    <h2 className="text-2xl font-bold mb-6">{title}</h2>
                    <p className="mb-6">{text}</p>
                    <Link href={href} className={BLUE_BUTTON}>{btn}</Link>
                </div>
                <div className="min-w-0">{children}</div>
            </div>
        </section>
    );
}

/** The home page's feature blocks: what each feature does, a real sample of it, and a way in. */
export function HomeShowcase({ content, user }: { content: HomeShowcaseContent; user: CurrentUser | null }) {
    const { streamers, lists, games, genres } = content;
    return (
        <Fragment>
            <Feature title={streamers.title} text={streamers.text} href="/streamers" btn={streamers.btn} border>
                <StreamersSample content={streamers} />
            </Feature>

            <section className="px-6 bg-gray-100">
                <div className="max-w-[1000] mx-auto py-14 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8 lg:gap-12">
                    <div className="min-w-0 lg:flex-1">
                        <h2 className="text-2xl font-bold mb-4">{lists.title}</h2>
                        <p>{lists.text}</p>
                    </div>
                    {user
                        ? <Link href="/dashboard" className={`${BLUE_BUTTON} self-start lg:self-auto shrink-0`}>{lists.open_btn}</Link>
                        // The dashboard would only redirect a logged-out visitor, or a crawler.
                        : <Link href={`/login?next=${encodeURIComponent("/dashboard")}`} rel="nofollow" prefetch={false}
                            className={`${TWITCH_BUTTON} self-start lg:self-auto shrink-0`}>{lists.login_btn}</Link>
                    }
                </div>
            </section>

            <Feature title={games.title} text={games.text} href="/games" btn={games.btn}>
                <GamesSample content={games} />
            </Feature>

            <Feature title={genres.title} text={genres.text} href="/genre-trends" btn={genres.btn} border>
                <GenresSample content={genres} />
            </Feature>
        </Fragment>
    );
}
