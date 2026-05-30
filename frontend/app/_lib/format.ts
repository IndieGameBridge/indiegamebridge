export function formatStreamTime(iso: string) {
    const d = new Date(iso);
    const date = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
    const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
    return `${date} • ${time}`;
}
