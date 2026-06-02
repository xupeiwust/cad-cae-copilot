import { forwardRef, useEffect, useRef, type TextareaHTMLAttributes } from "react";

type AutoResizeTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Optional cap on the auto-grown height (px). Omitted = no JS cap (CSS may
   *  still constrain), matching the original behavior. */
  maxHeight?: number;
};

/**
 * A textarea that grows with its content. Extracted verbatim from AgentInputBox:
 * on input, reset to "auto" then set to scrollHeight (capped at maxHeight when
 * given); when the value becomes empty, collapse back to "auto". Carries no
 * chat/agent/command knowledge. Forwards a ref so the parent can read the caret
 * and focus the element.
 */
export const AutoResizeTextarea = forwardRef<HTMLTextAreaElement, AutoResizeTextareaProps>(
  function AutoResizeTextarea({ value, onChange, maxHeight, ...rest }, ref) {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);

    const setRef = (el: HTMLTextAreaElement | null) => {
      innerRef.current = el;
      if (typeof ref === "function") ref(el);
      else if (ref) ref.current = el;
    };

    const resize = (el: HTMLTextAreaElement | null) => {
      if (!el) return;
      el.style.height = "auto";
      const next = maxHeight ? Math.min(el.scrollHeight, maxHeight) : el.scrollHeight;
      el.style.height = `${next}px`;
    };

    useEffect(() => {
      const el = innerRef.current;
      if (el && !value) el.style.height = "auto";
    }, [value]);

    return (
      <textarea
        ref={setRef}
        value={value}
        onChange={(event) => {
          onChange?.(event);
          resize(event.target);
        }}
        {...rest}
      />
    );
  },
);
