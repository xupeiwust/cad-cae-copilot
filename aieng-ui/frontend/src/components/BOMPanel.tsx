import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { BOMData } from "../types/bom";

type BOMPanelProps = {
  projectId?: string | null;
  onNotice?: (title: string, detail: string) => void;
};

export function BOMPanel({ projectId, onNotice }: BOMPanelProps) {
  const [bom, setBom] = useState<BOMData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<"csv" | "json">("csv");

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.generateBOM(projectId);
      setBom(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const exportBOM = useCallback(() => {
    if (!bom) return;
    const filename = `bom-${bom.projectId.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}`;
    if (exportFormat === "json") {
      const blob = new Blob([JSON.stringify(bom, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.json`;
      a.click();
      URL.revokeObjectURL(url);
      onNotice?.("Exported", `BOM saved as ${filename}.json`);
    } else {
      const headers = ["ID", "Name", "Quantity", "Material", "Standard Part", "Type", "Parameters"];
      const rows = bom.items.map((item) => [
        item.id,
        item.name,
        String(item.quantity),
        item.material ?? "",
        item.isStandardPart ? "Yes" : "No",
        item.standardPartType ?? "",
        item.parameters ? JSON.stringify(item.parameters) : "",
      ]);
      const csv = [headers.join(","), ...rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))].join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      onNotice?.("Exported", `BOM saved as ${filename}.csv`);
    }
  }, [bom, exportFormat, onNotice]);

  const summary = useMemo(() => {
    if (!bom) return null;
    return {
      total: bom.totalCount,
      standard: bom.standardPartCount,
      custom: bom.customPartCount,
    };
  }, [bom]);

  return (
    <section className="bom-panel" aria-label="Bill of materials">
      <div className="panel-head" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <strong style={{ fontSize: "14px", color: "var(--text-primary, #e5e5e5)" }}>Bill of Materials</strong>
          <span style={{ fontSize: "11px", color: "var(--text-secondary, #a3a3a3)" }}>
            {summary ? `${summary.total} items` : "—"}
          </span>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={() => void refresh()}
            disabled={loading || !projectId}
            style={{ fontSize: "11px", padding: "4px 10px" }}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value as "csv" | "json")}
            style={{ fontSize: "11px", padding: "4px 8px" }}
          >
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
          <button
            type="button"
            className="compact-button"
            onClick={() => exportBOM()}
            disabled={!bom}
            style={{ fontSize: "11px", padding: "4px 10px" }}
          >
            Export
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: "10px",
            borderRadius: "8px",
            background: "rgba(239, 68, 68, 0.08)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            color: "#fca5a5",
            fontSize: "12px",
          }}
        >
          {error}
        </div>
      )}

      {!projectId && (
        <div
          style={{
            padding: "12px",
            borderRadius: "8px",
            background: "rgba(245, 158, 11, 0.08)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
            color: "#fde68a",
            fontSize: "12px",
          }}
        >
          Select a project to view its BOM.
        </div>
      )}

      {bom && (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gap: "8px",
            }}
          >
            <StatPill label="Total" value={summary?.total ?? 0} />
            <StatPill label="Standard" value={summary?.standard ?? 0} />
            <StatPill label="Custom" value={summary?.custom ?? 0} />
          </div>

          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                fontSize: "11px",
                borderCollapse: "collapse",
                minWidth: "480px",
              }}
            >
              <thead>
                <tr style={{ borderBottom: "1px solid var(--glass-line, rgba(180, 196, 218, 0.16))" }}>
                  <th style={{ textAlign: "left", padding: "6px", color: "var(--text-tertiary, #737373)" }}>Name</th>
                  <th style={{ textAlign: "right", padding: "6px", color: "var(--text-tertiary, #737373)" }}>Qty</th>
                  <th style={{ textAlign: "left", padding: "6px", color: "var(--text-tertiary, #737373)" }}>Material</th>
                  <th style={{ textAlign: "left", padding: "6px", color: "var(--text-tertiary, #737373)" }}>Type</th>
                </tr>
              </thead>
              <tbody>
                {bom.items.map((item) => (
                  <tr
                    key={item.id}
                    style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)" }}
                  >
                    <td style={{ padding: "6px", color: "var(--text-primary, #e5e5e5)" }}>{item.name}</td>
                    <td style={{ padding: "6px", textAlign: "right", color: "var(--text-secondary, #a3a3a3)", fontFamily: "ui-monospace, monospace" }}>
                      {item.quantity}
                    </td>
                    <td style={{ padding: "6px", color: "var(--text-secondary, #a3a3a3)" }}>{item.material ?? "—"}</td>
                    <td style={{ padding: "6px" }}>
                      {item.isStandardPart ? (
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "1px 6px",
                            borderRadius: "999px",
                            background: "rgba(45, 212, 191, 0.12)",
                            color: "#2dd4bf",
                          }}
                        >
                          {item.standardPartType ?? "Standard"}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-tertiary, #737373)" }}>Custom</span>
                      )}
                    </td>
                  </tr>
                ))}
                {bom.items.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ padding: "16px", textAlign: "center", color: "var(--text-tertiary, #737373)" }}>
                      No items in BOM.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "2px",
        padding: "8px 10px",
        borderRadius: "8px",
        border: "1px solid var(--glass-line, rgba(180, 196, 218, 0.16))",
        background: "rgba(255, 255, 255, 0.04)",
      }}
    >
      <span style={{ fontSize: "10px", color: "var(--text-tertiary, #737373)", fontWeight: 600, textTransform: "uppercase" }}>
        {label}
      </span>
      <span style={{ fontSize: "14px", color: "var(--text-primary, #e5e5e5)", fontWeight: 700, fontFamily: "ui-monospace, monospace" }}>
        {value}
      </span>
    </div>
  );
}
