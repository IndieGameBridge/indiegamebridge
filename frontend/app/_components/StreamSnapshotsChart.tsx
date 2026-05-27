type Snapshot = { g: number; t: number; v: number };

type Props = {
    snapshots: Snapshot[];
    started_at: string;
    games: string[];
    host_game_ids: number[];
};

type Column = {
    kind: "data" | "gap";
    viewers: number;
    gameName: string;
    label: string;
};

const SLOT_MINUTES = 20;
const SLOT_SECONDS = SLOT_MINUTES * 60;

function formatElapsed(slotIndex: number): string {
    const totalMin = slotIndex * SLOT_MINUTES;
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    return `${h}:${m.toString().padStart(2, "0")}`;
}

function buildColumns(
    snapshots: Snapshot[],
    startedAt: string,
    games: string[],
    hostGameIds: number[],
): Column[] {
    if (snapshots.length === 0) return [];

    const startUnix = new Date(startedAt).getTime() / 1000;
    const sorted = [...snapshots].sort((a, b) => a.t - b.t);

    const nameFor = (g: number) => {
        const idx = hostGameIds.indexOf(g);
        return idx >= 0 ? games[idx] : "N/A";
    };

    const columns: Column[] = [];
    let prevSlot = 0;
    let prevGameName = "";

    for (const snap of sorted) {
        const rawSlot = Math.round((snap.t - startUnix) / SLOT_SECONDS);
        const slot = Math.max(prevSlot + 1, rawSlot);
        for (let s = prevSlot + 1; s < slot; s++) {
            columns.push({ kind: "gap", viewers: 0, gameName: prevGameName, label: formatElapsed(s) });
        }
        const name = nameFor(snap.g);
        columns.push({ kind: "data", viewers: snap.v, gameName: name, label: formatElapsed(slot) });
        prevSlot = slot;
        prevGameName = name;
    }

    return columns;
}

export function StreamSnapshotsChart({ snapshots, started_at, games, host_game_ids }: Props) {
    const columns = buildColumns(snapshots, started_at, games, host_game_ids);
    if (columns.length === 0) return null;

    const maxViewers = Math.max(
        ...columns.filter((c) => c.kind === "data").map((c) => c.viewers),
        1,
    );

    const paddingLeft = 12;
    const paddingRight = 12;
    const paddingTop = 22;
    const barsHeight = 160;
    const timeLabelGap = 4;
    const timeLabelHeight = 14;
    const gameRowGap = 6;
    const gameRowHeight = 28;
    const paddingBottom = 4;
    const height = paddingTop + barsHeight + timeLabelGap + timeLabelHeight + gameRowGap + gameRowHeight + paddingBottom;

    const colWidth = 40;
    const barGap = 2;
    const chartWidth = colWidth * columns.length + barGap * Math.max(0, columns.length - 1);
    const width = chartWidth + paddingLeft + paddingRight;

    const baselineY = paddingTop + barsHeight;
    const timeLabelY = baselineY + timeLabelGap + 10;
    const gameRowTop = baselineY + timeLabelGap + timeLabelHeight + gameRowGap;
    const gameRowTextY = gameRowTop + gameRowHeight / 2 + 4;

    const xFor = (i: number) => paddingLeft + i * (colWidth + barGap);

    type Segment = { start: number; end: number; name: string };
    const segments: Segment[] = [];
    for (let i = 0; i < columns.length; i++) {
        const name = columns[i].gameName;
        const last = segments[segments.length - 1];
        if (last && last.name === name) {
            last.end = i;
        } else {
            segments.push({ start: i, end: i, name });
        }
    }

    return (
        <div className="overflow-x-auto mb-4">
        <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Viewer counts across stream snapshots"
        >
            <line
                x1={paddingLeft}
                x2={paddingLeft + chartWidth}
                y1={baselineY}
                y2={baselineY}
                stroke="#e5e7eb"
            />

            {columns.map((col, i) => {
                const x = xFor(i);
                if (col.kind === "gap") {
                    return (
                        <rect
                            key={`col-${i}`}
                            x={x}
                            y={paddingTop}
                            width={colWidth}
                            height={barsHeight}
                            className="fill-gray-200"
                        />
                    );
                }
                const barH = (col.viewers / maxViewers) * barsHeight;
                return (
                    <rect
                        key={`col-${i}`}
                        x={x}
                        y={baselineY - barH}
                        width={colWidth}
                        height={barH}
                        className="fill-indigo-500"
                    />
                );
            })}

            {columns.map((col, i) => {
                const cx = xFor(i) + colWidth / 2;
                if (col.kind === "gap") {
                    return (
                        <text
                            key={`val-${i}`}
                            x={cx}
                            y={paddingTop - 6}
                            textAnchor="middle"
                            fontSize="12"
                            className="selection:fill-white"
                        >
                            no data
                        </text>
                    );
                }
                const barH = (col.viewers / maxViewers) * barsHeight;
                return (
                    <text
                        key={`val-${i}`}
                        x={cx}
                        y={baselineY - barH - 4}
                        textAnchor="middle"
                        fontSize="12"
                        className="selection:fill-white"
                    >
                        {col.viewers.toLocaleString()}
                    </text>
                );
            })}

            {columns.map((col, i) => (
                <text
                    key={`time-${i}`}
                    x={xFor(i) + colWidth / 2}
                    y={timeLabelY}
                    textAnchor="middle"
                    fontSize="12"
                    className="selection:fill-white"
                >
                    {col.label}
                </text>
            ))}

            <line
                x1={paddingLeft}
                x2={paddingLeft + chartWidth}
                y1={gameRowTop}
                y2={gameRowTop}
                stroke="#e5e7eb"
            />
            <line
                x1={paddingLeft}
                x2={paddingLeft + chartWidth}
                y1={gameRowTop + gameRowHeight}
                y2={gameRowTop + gameRowHeight}
                stroke="#e5e7eb"
            />

            {segments.map((seg, idx) => {
                const xStart = xFor(seg.start);
                const xEnd = xFor(seg.end) + colWidth;
                const midX = (xStart + xEnd) / 2;
                const gameFontSize = 14;
                const segmentInnerPadding = 4;
                const approxCharWidth = gameFontSize * 0.55;
                const innerWidth = (xEnd - xStart) - segmentInnerPadding * 2;
                const maxChars = Math.max(1, Math.floor(innerWidth / approxCharWidth));
                const displayName = seg.name.length > maxChars
                    ? seg.name.slice(0, Math.max(1, maxChars - 1)) + "…"
                    : seg.name;
                return (
                    <g key={`game-${idx}`}>
                        {seg.name && (
                            <text
                                x={midX}
                                y={gameRowTextY}
                                textAnchor="middle"
                                fontSize={gameFontSize}
                                className="selection:fill-white"
                            >
                                <title>{seg.name}</title>
                                {displayName}
                            </text>
                        )}
                        {idx > 0 && segments[idx - 1].name !== "" && (
                            <line
                                x1={xStart - barGap / 2}
                                x2={xStart - barGap / 2}
                                y1={gameRowTop}
                                y2={gameRowTop + gameRowHeight}
                                stroke="#6b7280"
                                strokeWidth="1"
                            />
                        )}
                    </g>
                );
            })}
        </svg>
        </div>
    );
}
