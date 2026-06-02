// Brand mark. Drawn with currentColor, so set the color via a text-* class on
// the element (e.g. text-white) or its parent.
export function IndieGameBridgeMark({ className }: { className?: string }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 96 96"
            className={className}
            aria-hidden="true"
            focusable="false"
        >
            <g fill="currentColor" stroke="currentColor" strokeLinecap="round">
                <rect x="10" y="56" width="6" height="22" rx="1" />
                <rect x="80" y="56" width="6" height="22" rx="1" />
                <line x1="6" y1="78" x2="90" y2="78" strokeWidth="3" />
                <rect x="9" y="60" width="8" height="10" rx="1.5" stroke="none" />
                <rect x="19" y="52" width="8" height="18" rx="1.5" stroke="none" />
                <rect x="29" y="44" width="8" height="26" rx="1.5" stroke="none" />
                <rect x="39" y="36" width="8" height="34" rx="1.5" stroke="none" />
                <rect x="49" y="42" width="8" height="28" rx="1.5" stroke="none" />
                <rect x="59" y="48" width="8" height="22" rx="1.5" stroke="none" />
                <rect x="69" y="54" width="8" height="16" rx="1.5" stroke="none" />
                <rect x="79" y="58" width="8" height="12" rx="1.5" stroke="none" />
                <line x1="6" y1="72" x2="90" y2="72" strokeWidth="3" />
            </g>
        </svg>
    );
}
