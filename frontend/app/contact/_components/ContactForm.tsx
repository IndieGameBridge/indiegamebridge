"use client";

import { useEffect, useRef, useState } from "react";

import type { ContactFormCopy } from "../page";

// Cloudflare Turnstile attaches its API to window once its script loads.
type TurnstileApi = {
    render: (
        el: HTMLElement,
        opts: {
            sitekey: string;
            callback: (token: string) => void;
            "expired-callback"?: () => void;
            "error-callback"?: () => void;
        },
    ) => string;
    reset: (widgetId?: string) => void;
};

declare global {
    interface Window {
        turnstile?: TurnstileApi;
    }
}

const TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

// Kept in sync with the backend column limits (apps/contact/views.py).
const SUBJECT_MAX = 200;
const MESSAGE_MAX = 5000;

type Status = "idle" | "sending" | "success" | "error";

export function ContactForm({
    copy,
    turnstileSiteKey,
}: {
    copy: ContactFormCopy;
    turnstileSiteKey: string;
}) {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [subject, setSubject] = useState("");
    const [message, setMessage] = useState("");
    // Honeypot: real users never see or fill this; bots that fill every field do.
    const [company, setCompany] = useState("");

    const [status, setStatus] = useState<Status>("idle");
    const [errorText, setErrorText] = useState("");

    const widgetRef = useRef<HTMLDivElement>(null);
    const widgetId = useRef<string | null>(null);
    const [turnstileToken, setTurnstileToken] = useState("");

    // Render the Turnstile widget once its script has loaded. Skipped entirely
    // when no site key is configured (e.g. local dev) - the backend likewise
    // skips verification, so the form stays usable.
    useEffect(() => {
        if (!turnstileSiteKey) return;

        let cancelled = false;

        const renderWidget = () => {
            if (cancelled || !window.turnstile || !widgetRef.current || widgetId.current) return;
            widgetId.current = window.turnstile.render(widgetRef.current, {
                sitekey: turnstileSiteKey,
                callback: (token) => setTurnstileToken(token),
                "expired-callback": () => setTurnstileToken(""),
                "error-callback": () => setTurnstileToken(""),
            });
        };

        if (window.turnstile) {
            renderWidget();
        } else if (!document.querySelector(`script[src="${TURNSTILE_SCRIPT}"]`)) {
            const script = document.createElement("script");
            script.src = TURNSTILE_SCRIPT;
            script.async = true;
            script.defer = true;
            script.onload = renderWidget;
            document.head.appendChild(script);
        } else {
            // Script tag exists but API not ready yet — poll briefly.
            const interval = setInterval(() => {
                if (window.turnstile) {
                    clearInterval(interval);
                    renderWidget();
                }
            }, 100);
            return () => {
                cancelled = true;
                clearInterval(interval);
            };
        }

        return () => {
            cancelled = true;
        };
    }, [turnstileSiteKey]);

    const isSending = status === "sending";

    async function handleSubmit(event: React.FormEvent) {
        event.preventDefault();
        setErrorText("");

        if (!name.trim() || !email.trim() || !message.trim()) {
            setStatus("error");
            setErrorText(copy.validation_text);
            return;
        }
        if (turnstileSiteKey && !turnstileToken) {
            setStatus("error");
            setErrorText(copy.captcha_text);
            return;
        }

        setStatus("sending");
        try {
            const response = await fetch("/api/contact/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name,
                    email,
                    subject,
                    message,
                    company,
                    turnstile_token: turnstileToken,
                }),
            });

            if (response.ok) {
                setStatus("success");
                return;
            }

            setStatus("error");
            setErrorText(copy.error_text);
            // Token is single-use; let the user solve a fresh challenge on retry.
            setTurnstileToken("");
            if (turnstileSiteKey && window.turnstile && widgetId.current) {
                window.turnstile.reset(widgetId.current);
            }
        } catch {
            setStatus("error");
            setErrorText(copy.error_text);
        }
    }

    if (status === "success") {
        return (
            <p className="text-center text-green-700 border border-green-600 rounded p-4" role="status">
                {copy.success_text}
            </p>
        );
    }

    const inputClass = "w-full text-sm p-2 border border-gray-300 rounded-sm outline-gray-400";

    return (
        <form className="flex flex-col gap-x-6 gap-y-5" onSubmit={handleSubmit} noValidate>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-x-6 gap-y-5">
                <div>
                    <label htmlFor="contact-name" className="block text-sm text-brand-blue mb-1">{copy.name_label}</label>
                    <input id="contact-name" type="text" name="name" value={name} required maxLength={120}
                        autoComplete="name" placeholder={copy.name_placeholder} className={inputClass}
                        onChange={(e) => setName(e.target.value)} />
                </div>

                <div>
                    <label htmlFor="contact-email" className="block text-sm text-brand-blue mb-1">{copy.email_label}</label>
                    <input id="contact-email" type="email" name="email" value={email} required maxLength={254}
                        autoComplete="email" placeholder={copy.email_placeholder} className={inputClass}
                        onChange={(e) => setEmail(e.target.value)} />
                </div>
            </div>

            <div>
                <div className="flex items-baseline justify-between mb-1">
                    <label htmlFor="contact-subject" className="text-sm text-brand-blue">{copy.subject_label}</label>
                    <span className="text-xs text-gray-400">{subject.length}/{SUBJECT_MAX}</span>
                </div>
                <input id="contact-subject" type="text" name="subject" value={subject} maxLength={SUBJECT_MAX}
                    placeholder={copy.subject_placeholder} className={inputClass}
                    onChange={(e) => setSubject(e.target.value)} />
            </div>

            <div>
                <div className="flex items-baseline justify-between mb-1">
                    <label htmlFor="contact-message" className="text-sm text-brand-blue">{copy.message_label}</label>
                    <span className="text-xs text-gray-400">{message.length}/{MESSAGE_MAX}</span>
                </div>
                <textarea id="contact-message" name="message" value={message} required rows={6} maxLength={MESSAGE_MAX}
                    placeholder={copy.message_placeholder} className={`${inputClass} resize-y`}
                    onChange={(e) => setMessage(e.target.value)} />
            </div>

            {/* Honeypot: hidden from users (and assistive tech), tempting to bots. */}
            <div aria-hidden="true" className="hidden">
                <label htmlFor="contact-company">Company</label>
                <input id="contact-company" type="text" name="company" tabIndex={-1} autoComplete="off"
                    value={company} onChange={(e) => setCompany(e.target.value)} />
            </div>

            {turnstileSiteKey ? <div ref={widgetRef} className="flex justify-center" /> : null}

            {status === "error" ? (
                <p className="text-sm text-red-600" role="alert">{errorText}</p>
            ) : null}

            <div className="text-center pt-4">
                <button type="submit" disabled={isSending}
                    className={`text-sm px-8 py-2 rounded-sm text-white ${isSending
                        ? "bg-gray-300 cursor-not-allowed"
                        : "bg-blue-600 hover:bg-blue-700 cursor-pointer"
                    }`}>
                    {isSending ? copy.sending_text : copy.submit_text}
                </button>
            </div>
            
        </form>
    );
}
