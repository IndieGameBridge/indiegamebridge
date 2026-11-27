// A game page's month by month section: its past months, counted from the archive files, for
// all the page languages and then a table for each language. The API writes the text and the
// numbers; a hidden number shows as a dash, which says why on hover and to screen readers.

import { ShareBars, ShareBarsContent } from "./GameCharts";

type HistoryTableContent = {
    columns: { label: string; numeric: boolean }[];
    // Newest month first; a row's cells follow the columns after Month.
    rows: { month: string; cells: string[] }[];
};

export type GameHistoryContent = {
    title: string;
    caption: string;
    text: string;
    bars: ShareBarsContent;
    table: HistoryTableContent;
    by_language: {
        title: string;
        caption: string;
        tables: { heading: string; text: string; table: HistoryTableContent }[];
        others: string | null;
    } | null;
    // The dash a hidden number shows, and why it's hidden.
    hidden: string;
    hidden_hint: string;
    notes: string[];
};

/** A table of months, scrolling sideways inside its frame on a narrow screen. */
function HistoryTable({ table, caption, hidden, hiddenHint }: {
    table: HistoryTableContent;
    caption: string;
    hidden: string;
    hiddenHint: string;
}) {
    return (
        // Relative, so the screen readers' texts, placed absolutely, stay inside the scrolling
        // frame: otherwise they widen the whole page on a phone.
        <div className="relative overflow-x-auto border border-gray-300 rounded-lg">
            <table className="w-full min-w-205 border-collapse text-sm">
                <caption className="sr-only">{caption}</caption>
                <thead>
                    <tr className="bg-gray-50 border-b border-gray-300">
                        {table.columns.map((column) => (
                            <th
                                key={column.label}
                                scope="col"
                                className={`px-3 py-2.5 font-bold whitespace-nowrap ${column.numeric ? "text-right" : "text-left"}`}
                            >
                                {column.label}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {table.rows.map((row) => (
                        <tr key={row.month} className="border-b border-gray-200 last:border-b-0">
                            <th scope="row" className="px-3 py-2.5 text-left font-normal whitespace-nowrap">{row.month}</th>
                            {row.cells.map((cell, index) => (
                                <td
                                    key={table.columns[index + 1]?.label ?? index}
                                    // Numbers stay on one line; words, such as the main languages, may wrap.
                                    className={`px-3 py-2.5 ${table.columns[index + 1]?.numeric ? "text-right tabular-nums whitespace-nowrap" : "text-left"}`}
                                    title={cell === hidden ? hiddenHint : undefined}
                                >
                                    {cell === hidden
                                        ? <><span aria-hidden="true">{cell}</span><span className="sr-only">{hiddenHint}</span></>
                                        : cell}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function GameHistory({ history }: { history: GameHistoryContent }) {
    const tableProps = { hidden: history.hidden, hiddenHint: history.hidden_hint };
    return (
        <section className="flex flex-col gap-7">
            <div>
                <h2 className="text-xl font-bold mb-2">{history.title}</h2>
                <p className="text-sm text-gray-600">{history.caption}</p>
            </div>
            {history.text && <p className="max-w-205">{history.text}</p>}
            <ShareBars content={history.bars} labelWidth="w-22" heading="h3" className="max-w-160" />
            <HistoryTable table={history.table} caption={history.title} {...tableProps} />
            {history.by_language && (
                <div className="flex flex-col gap-7 pt-3">
                    <div>
                        <h3 className="text-lg font-bold mb-2">{history.by_language.title}</h3>
                        <p className="text-sm text-gray-600">{history.by_language.caption}</p>
                    </div>
                    {history.by_language.tables.map((one) => (
                        <div key={one.heading} className="flex flex-col gap-2.5">
                            <h4 className="text-base font-bold">{one.heading}</h4>
                            <p className="text-sm">{one.text}</p>
                            <HistoryTable table={one.table} caption={one.heading} {...tableProps} />
                        </div>
                    ))}
                    {history.by_language.others && <p className="text-sm">{history.by_language.others}</p>}
                </div>
            )}
            <ul className="list-disc pl-5 text-sm text-gray-700 flex flex-col gap-1.5">
                {history.notes.map((note) => <li key={note}>{note}</li>)}
            </ul>
        </section>
    );
}
