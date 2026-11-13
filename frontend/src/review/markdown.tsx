// The small part of Markdown the tutor is asked to write (see chat.system.md):
// paragraphs, lists, headings, bold, italics, inline code and KaTeX maths.
// Parsed into data and rendered as React nodes, never as HTML, so nothing the
// model writes can inject markup.
import katex from "katex";
import type { ReactNode } from "react";

export type Inline = { kind: "text" | "bold" | "italic" | "code" | "math"; text: string };

const INLINE = /(\$[^$\n]+\$|`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\s][^*\n]*?\*)/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    if (part.length > 2 && part.startsWith("$") && part.endsWith("$")) out.push({ kind: "math", text: part.slice(1, -1) });
    else if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) out.push({ kind: "code", text: part.slice(1, -1) });
    else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) out.push({ kind: "bold", text: part.slice(2, -2) });
    else if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) out.push({ kind: "italic", text: part.slice(1, -1) });
    else out.push({ kind: "text", text: part });
  }
  return out;
}

export type Block =
  | { kind: "paragraph" | "heading" | "math"; text: string }
  | { kind: "bullets" | "numbers"; items: string[] };

export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = [];
  const lines = markdown.replace(/\r/g, "").split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (line.startsWith("$$")) {
      // A formula on its own: up to the closing $$, on this line or a later one.
      let body = line.slice(2);
      while (!body.includes("$$") && i + 1 < lines.length) body += "\n" + lines[++i];
      blocks.push({ kind: "math", text: body.split("$$")[0].trim() });
      continue;
    }
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", text: heading[1] });
      continue;
    }
    const bullet = /^[-*•]\s+(.*)$/, number = /^\d+[.)]\s+(.*)$/;
    const list = bullet.test(line) ? bullet : number.test(line) ? number : null;
    if (list) {
      const items: string[] = [];
      for (; i < lines.length && list.test(lines[i].trim()); i++) items.push(list.exec(lines[i].trim())![1]);
      i--;
      blocks.push({ kind: list === bullet ? "bullets" : "numbers", items });
      continue;
    }
    const text = [line];
    while (i + 1 < lines.length && lines[i + 1].trim() && !/^(\$\$|#{1,4}\s|[-*•]\s|\d+[.)]\s)/.test(lines[i + 1].trim())) text.push(lines[++i].trim());
    blocks.push({ kind: "paragraph", text: text.join(" ") });
  }
  return blocks;
}

const math = (source: string, display: boolean) => ({
  __html: katex.renderToString(source, { throwOnError: false, displayMode: display, strict: "ignore" }),
});

function Spans({ text, nested = false }: { text: string; nested?: boolean }): ReactNode {
  return parseInline(text).map((part, i) => {
    if (part.kind === "math") return <span key={i} dangerouslySetInnerHTML={math(part.text, false)} />;
    if (part.kind === "code") return <code key={i}>{part.text}</code>;
    // One level of nesting, so "**el paso $x$**" keeps its formula.
    if (part.kind === "bold") return <strong key={i}>{nested ? part.text : <Spans text={part.text} nested />}</strong>;
    if (part.kind === "italic") return <em key={i}>{nested ? part.text : <Spans text={part.text} nested />}</em>;
    return <span key={i}>{part.text}</span>;
  });
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="markdown">
      {parseBlocks(source).map((block, i) => {
        if ("items" in block) {
          const items = block.items.map((item, n) => <li key={n}><Spans text={item} /></li>);
          return block.kind === "bullets" ? <ul key={i}>{items}</ul> : <ol key={i}>{items}</ol>;
        }
        if (block.kind === "math") return <div key={i} className="latex" dangerouslySetInnerHTML={math(block.text, true)} />;
        if (block.kind === "heading") return <h4 key={i}><Spans text={block.text} /></h4>;
        return <p key={i}><Spans text={block.text} /></p>;
      })}
    </div>
  );
}
