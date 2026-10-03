type Block =
  | { kind: "h1"; text: string }
  | { kind: "h2"; text: string }
  | { kind: "p"; text: string }
  | { kind: "li"; text: string }
  | { kind: "ref"; number: string; url: string };

function lineBlock(line: string): Block[] {
  const text = line.trim();
  if (!text) return [];
  if (text.startsWith("# ")) return [{ kind: "h1", text: text.slice(2) }];
  if (text.startsWith("## ")) return [{ kind: "h2", text: text.slice(3) }];
  if (text.startsWith("- ")) return [{ kind: "li", text: text.slice(2) }];
  const reference = text.match(/^(\d+)\.\s+(https?:\/\/\S+)/);
  if (reference) return [{ kind: "ref", number: reference[1], url: reference[2] }];
  return [{ kind: "p", text }];
}

function blocks(markdown: string): Block[] {
  return markdown.split(/\r?\n/).flatMap(lineBlock);
}

function Rich({ text }: { text: string }) {
  const parts = text.split(/(\[\d+(?:\s*,\s*\d+)*\]|https?:\/\/\S+)/g);
  return (
    <>
      {parts.map((part, index) => {
        const cite = part.match(/^\[(\d+(?:\s*,\s*\d+)*)\]$/);
        if (cite) {
          const numbers = cite[1].split(/\s*,\s*/);
          return (
            <sup key={index} className="ml-1 font-mono text-[10px] tracking-wide text-[#e2a15a]">
              {numbers.map((number, position) => (
                <a key={number} href={`#ref-${number}`} className="hover:underline">
                  {position > 0 ? ", " : ""}
                  {number}
                </a>
              ))}
            </sup>
          );
        }
        if (part.startsWith("http")) {
          return (
            <a key={index} href={part} className="break-all text-[#e2a15a] underline decoration-[#5a4630] underline-offset-4">
              {part}
            </a>
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function ReportView({ markdown }: { markdown: string }) {
  const items = blocks(markdown);
  const title = items.find((item) => item.kind === "h1");
  return (
    <article className="mt-6 border-t border-[#3a3228] pt-8">
      {title?.kind === "h1" ? (
        <h3 className="font-serif text-4xl leading-tight text-[#f3eadc]">{title.text}</h3>
      ) : null}
      {items.map((item, index) => {
        if (item.kind === "h1") return null;
        if (item.kind === "h2") {
          return (
            <h4 key={index} className="mt-10 font-serif text-2xl text-[#f3eadc]">
              {item.text}
            </h4>
          );
        }
        if (item.kind === "li") {
          return (
            <p key={index} className="mt-3 border-l border-[#3a3228] pl-4 text-[15px] leading-7 text-[#f3eadc]">
              <Rich text={item.text} />
            </p>
          );
        }
        if (item.kind === "ref") {
          return (
            <p key={index} id={`ref-${item.number}`} className="mt-3 flex gap-3 text-sm leading-6">
              <span className="w-6 shrink-0 font-mono text-[#e2a15a]">{item.number}</span>
              <a href={item.url} className="min-w-0 text-[#cbbba6] hover:text-[#f3eadc]">
                <span className="block text-[#f3eadc]">{host(item.url)}</span>
                <span className="block break-all text-[#a89880]">{item.url}</span>
              </a>
            </p>
          );
        }
        return (
          <p key={index} className="mt-4 text-[15px] leading-8 text-[#e7dccb]">
            <Rich text={item.text} />
          </p>
        );
      })}
    </article>
  );
}
