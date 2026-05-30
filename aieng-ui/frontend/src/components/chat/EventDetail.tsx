type EventDetailProps = {
  detail?: unknown;
  label?: string;
};

export function EventDetail({ detail, label = "Details" }: EventDetailProps) {
  if (detail == null) return null;
  return (
    <details className="event-detail">
      <summary>{label}</summary>
      <pre>{formatDetail(detail)}</pre>
    </details>
  );
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}
