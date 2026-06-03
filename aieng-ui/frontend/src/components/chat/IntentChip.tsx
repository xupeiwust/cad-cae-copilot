import { AlertTriangle, HelpCircle, Wand2 } from "lucide-react";

import type { TranscriptIntentLine } from "../../app/chatTranscript";
import type { ResolvedParamBinding } from "../../app/resolvedIntent";

type IntentChipProps = {
  item: TranscriptIntentLine;
};

const SOURCE_LABEL: Record<string, string> = {
  llm_classifier: "AI",
  keyword_heuristic: "keywords",
};

function formatValue(value: number | null, unit: string | null): string {
  if (value == null) return "";
  const shown = Number.isInteger(value) ? String(value) : String(value);
  return ` → ${shown}${unit ?? ""}`;
}

function BindingPill({ binding }: { binding: ResolvedParamBinding }) {
  const target = `${binding.slotName}${formatValue(binding.value, binding.unit)}`;
  if (binding.known === true) {
    const outOfRange = binding.withinBounds === false;
    return (
      <span className={`intent-binding intent-binding-known${outOfRange ? " intent-binding-warn" : ""}`}>
        {target}
        {binding.cadParameterName ? <code>{binding.cadParameterName}</code> : null}
        {outOfRange ? <AlertTriangle className="intent-binding-warn-icon" /> : null}
      </span>
    );
  }
  if (binding.known === false) {
    const why = binding.reason?.startsWith("ambiguous") ? "ambiguous" : "no match";
    return <span className="intent-binding intent-binding-unresolved">{target} · {why}</span>;
  }
  return <span className="intent-binding intent-binding-unverified">{target} · unverified</span>;
}

/**
 * Renders the backend-resolved natural-language intent as a compact chip
 * ("Understood as /modify") instead of the raw agent-facing instruction text.
 * The clarification variant flags an actionable-but-ambiguous intent so the user
 * knows the agent is confirming before acting.
 */
export function IntentChip({ item }: IntentChipProps) {
  const { command, source, confidence, needsClarification, bindings } = item.intent;

  if (needsClarification) {
    return (
      <div className="transcript-intent-line transcript-intent-clarify">
        <HelpCircle className="transcript-status-icon" />
        <span>
          Intent unclear — confirming before acting (looks like <code>/{command}</code>).
        </span>
      </div>
    );
  }

  return (
    <div className="transcript-intent-line">
      <Wand2 className="transcript-status-icon" />
      <span>
        Understood as <code>/{command}</code>
      </span>
      <span className="transcript-intent-source">
        via {SOURCE_LABEL[source] ?? source} · {Math.round(confidence * 100)}%
      </span>
      {bindings.length ? (
        <span className="transcript-intent-bindings">
          {bindings.map((binding, index) => (
            <BindingPill key={`${binding.slotName}-${index}`} binding={binding} />
          ))}
        </span>
      ) : null}
    </div>
  );
}
