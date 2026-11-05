"use client";

import type { ComponentProps } from "react";
import Link, { useLinkStatus } from "next/link";

function LinkProgress() {
    const { pending } = useLinkStatus();
    return pending ? <span aria-hidden="true" className="link-progress" /> : null;
}

/**
 * A Link that shows a thin bar across the top of the window while its page loads. Every page
 * is rendered on request, so a click would otherwise show nothing until the server answers.
 */
export function ProgressLink({ children, ...props }: ComponentProps<typeof Link>) {
    return (
        <Link {...props}>
            {children}
            <LinkProgress />
        </Link>
    );
}
