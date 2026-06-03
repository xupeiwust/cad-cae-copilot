import { useMemo } from "react";

import {
  editDraftForParameter,
  formatNumber,
  formatRange,
  groupParametersByScope,
  SCOPE_HINT,
  SCOPE_LABEL,
  type ParameterScope,
} from "../app/editableParameters";
import type { EditableParameter } from "../types";

type EditableParametersPanelProps = {
  parameters: EditableParameter[];
  /** Prefill the composer with a "/modify set <name> to " draft for a parameter. */
  onUseInChat?: (draft: string) => void;
};

/**
 * The "point" half of point-and-shoot editing: a read-only listing of the CAD
 * parameters that can be edited fast via cad.edit_parameter, grouped by editing
 * scope (local = safe single-part edit, global = shared/ripples). Clicking a
 * parameter drafts a /modify into the composer — the edit itself still flows
 * through the existing approval-gated path (this panel never mutates geometry).
 */
export function EditableParametersPanel({ parameters, onUseInChat }: EditableParametersPanelProps) {
  const groups = useMemo(() => groupParametersByScope(parameters), [parameters]);

  if (!parameters.length) return null;

  return (
    <section className="editparams-card" aria-label="Editable parameters">
      <div className="editparams-head">
        <strong>Editable parameters</strong>
        <span>{parameters.length}</span>
      </div>

      {groups.map((group) => (
        <div key={group.scope} className="editparams-group">
          <div
            className={`editparams-scope editparams-scope-${group.scope as ParameterScope}`}
            title={SCOPE_HINT[group.scope]}
          >
            {SCOPE_LABEL[group.scope]}
            <span className="editparams-scope-count">{group.parameters.length}</span>
          </div>

          {group.parameters.map((param: EditableParameter) => {
            const range = formatRange(param.min_value, param.max_value);
            const value = formatNumber(param.current_value);
            return (
              <div key={`${param.feature_id ?? "f"}:${param.parameter_name}`} className="editparams-row">
                <button
                  type="button"
                  className="editparams-name"
                  onClick={() => onUseInChat?.(editDraftForParameter(param))}
                  disabled={!onUseInChat}
                  title={
                    onUseInChat
                      ? `Draft a /modify for ${param.parameter_name}`
                      : param.parameter_name
                  }
                >
                  {param.parameter_name.replace(/_/g, " ")}
                </button>
                <code className="editparams-const" title={`constant ${param.cad_parameter_name}`}>
                  {param.cad_parameter_name}
                </code>
                <span className="editparams-value">{value || "—"}</span>
                {range ? <span className="editparams-range" title="allowed range">{range}</span> : null}
                <span className="editparams-feature" title={`feature ${param.feature_name}`}>
                  {param.feature_name}
                </span>
              </div>
            );
          })}
        </div>
      ))}

      <div className="editparams-foot">
        Click a parameter to draft a <code>/modify</code> — edits run through approval.
      </div>
    </section>
  );
}
