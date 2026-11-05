// JSON for a <script type="application/ld+json">, with "<" escaped so no text in it
// can close the script tag.
export function jsonLd(data: object): string {
    return JSON.stringify(data).replace(/</g, "\\u003c");
}
