"use client";

import { useEffect } from "react";

type OptOutSuccessContent = {
    already_optout: string;
    success_optout: string;
};

export function OptOutSuccess({ content, isNewOptOut }: { content: OptOutSuccessContent; isNewOptOut?: string; }) {
    // Strip ?status=done so a refresh shows the default opt-out view rather
    // than the success message again — we deliberately keep no client-side
    // flag so the success copy only renders during this one navigation.
    useEffect(() => {
        window.history.replaceState(null, "", "/optout");
    }, []);

    return (
        <p className="text-gray-600 mb-8">{isNewOptOut === 'yes' ? content.success_optout : content.already_optout}</p>
    );
}
