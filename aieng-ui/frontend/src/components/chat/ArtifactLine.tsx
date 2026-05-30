import { Box, FileText, RefreshCw } from "lucide-react";

import type { TranscriptArtifactLine } from "../../app/chatTranscript";
import { isLowRiskArtifactPath } from "../../appUtils";
import { PointerText } from "../PointerText";
import { EventDetail } from "./EventDetail";

type ArtifactLineProps = {
  item: TranscriptArtifactLine;
  onViewArtifact(path: string): void;
};

export function ArtifactLine({ item, onViewArtifact }: ArtifactLineProps) {
  return (
    <div className="artifact-line">
      {item.previewUrl ? <RefreshCw className="transcript-status-icon" /> : <Box className="transcript-status-icon" />}
      <span><PointerText text={item.summary} /></span>
      {item.previewFormat ? <code>{item.previewFormat}</code> : null}
      {item.partsAdded?.length || item.namedParts?.length ? (
        <div className="artifact-chip-row">
          {(item.partsAdded?.length ? item.partsAdded : item.namedParts ?? []).slice(0, 12).map((part) => (
            <span key={part} className="artifact-chip">{part}</span>
          ))}
        </div>
      ) : null}
      {item.artifactPaths?.filter(isLowRiskArtifactPath).length ? (
        <div className="artifact-link-row">
          {item.artifactPaths.filter(isLowRiskArtifactPath).slice(0, 8).map((path) => (
            <button key={path} type="button" className="ghost-button transcript-artifact-button" onClick={() => onViewArtifact(path)}>
              <FileText className="button-icon" />
              {path}
            </button>
          ))}
        </div>
      ) : null}
      <EventDetail detail={item.detail} />
    </div>
  );
}
