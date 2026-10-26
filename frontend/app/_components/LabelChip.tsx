export type ListLabel = {
    id: number;
    title: string;
    color: string;
};

// Label colours are the owner's own pick, so the chip's text follows its
// background: black once that is bright enough to out-contrast white (WCAG
// relative luminance above ~0.179), white otherwise.
function labelTextColor(hex: string): string {
    const [r, g, b] = [1, 3, 5].map((start) => {
        const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? "#000000" : "#ffffff";
}

export function LabelChip({ label }: { label: ListLabel }) {
    return (
        <span
            className="py-0.5 px-2 rounded-sm text-xs"
            style={{ backgroundColor: label.color, color: labelTextColor(label.color) }}
        >
            {label.title}
        </span>
    );
}
