import { useEffect, useRef, useState } from "react";

// Open state for a menu that hangs off a button. A click anywhere outside it,
// or Escape, closes it; Escape also hands focus back to the button, so keyboard
// users end up where they started.
export function useDropdown() {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    const buttonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!open) return;
        function handlePointerDown(event: PointerEvent) {
            if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
        }
        function handleKeyDown(event: KeyboardEvent) {
            if (event.key !== "Escape") return;
            setOpen(false);
            buttonRef.current?.focus();
        }
        document.addEventListener("pointerdown", handlePointerDown);
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("pointerdown", handlePointerDown);
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, [open]);

    return { open, setOpen, rootRef, buttonRef };
}
