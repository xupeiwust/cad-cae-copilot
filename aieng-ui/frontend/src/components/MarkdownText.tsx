import { Fragment, type ReactNode } from "react";
import { PointerText } from "./PointerText";

type MarkdownTextProps = {
  text: string | null | undefined;
  className?: string;
};

type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "code"; text: string };

const INLINE_RE = /(`[^`]+`|\*\*[^*]+\*\*)/g;

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      i += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length <= 2 ? 2 : 3, text: heading[2] });
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith("```") &&
      !/^(#{1,3})\s+/.test(lines[i].trim()) &&
      !/^[-*]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim())
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE_RE)) {
    const start = match.index ?? 0;
    if (start > last) {
      parts.push(<PointerText key={`t-${last}`} text={text.slice(last, start)} />);
    }
    const token = match[0];
    if (token.startsWith("`")) {
      parts.push(<code key={`c-${start}`}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      parts.push(<strong key={`b-${start}`}><PointerText text={token.slice(2, -2)} /></strong>);
    }
    last = start + token.length;
  }
  if (last < text.length) {
    parts.push(<PointerText key={`t-${last}`} text={text.slice(last)} />);
  }
  return <>{parts}</>;
}

export function MarkdownText({ text, className }: MarkdownTextProps) {
  if (!text) return null;
  const blocks = parseBlocks(text);
  return (
    <div className={className ? `markdown-text ${className}` : "markdown-text"}>
      {blocks.map((block, idx) => {
        if (block.kind === "heading") {
          const Tag = block.level === 2 ? "h2" : "h3";
          return <Tag key={idx}>{renderInline(block.text)}</Tag>;
        }
        if (block.kind === "paragraph") {
          return <p key={idx}>{renderInline(block.text)}</p>;
        }
        if (block.kind === "ul") {
          return (
            <ul key={idx}>
              {block.items.map((item, itemIdx) => <li key={itemIdx}>{renderInline(item)}</li>)}
            </ul>
          );
        }
        if (block.kind === "ol") {
          return (
            <ol key={idx}>
              {block.items.map((item, itemIdx) => <li key={itemIdx}>{renderInline(item)}</li>)}
            </ol>
          );
        }
        return (
          <pre key={idx}>
            <code>{block.text}</code>
          </pre>
        );
      })}
      {blocks.length === 0 ? <Fragment /> : null}
    </div>
  );
}
