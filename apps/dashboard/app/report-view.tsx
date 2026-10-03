import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function citeLinks(markdown: string) {
  return markdown.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_match, group: string) =>
    group
      .split(/\s*,\s*/)
      .map((number) => `[${number}](#ref-${number})`)
      .join(" "),
  );
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function references(section: string) {
  return section.split(/\r?\n/).flatMap((line) => {
    const match = line.trim().match(/^(\d+)\.\s+(.+)$/);
    if (!match) return [];
    const url = match[2].match(/https?:\/\/\S+/)?.[0]?.replace(/[.,);]+$/, "") ?? "";
    if (!url) return [];
    const title = match[2].replace(url, "").replace(/[,\s]+$/, "").trim();
    return [{ number: match[1], url, title }];
  });
}

const components: Components = {
  h1: ({ children }) => (
    <h3 className="max-w-[18ch] font-serif text-4xl leading-[1.15] text-balance text-foreground md:text-5xl">
      {children}
    </h3>
  ),
  h2: ({ children }) => (
    <h4 className="mt-12 font-serif text-3xl leading-tight text-foreground">{children}</h4>
  ),
  h3: ({ children }) => (
    <h5 className="mt-8 font-serif text-xl leading-snug text-foreground">{children}</h5>
  ),
  p: ({ children }) => (
    <p className="mt-4 max-w-[68ch] font-serif text-[17px] leading-8 text-muted-foreground">{children}</p>
  ),
  ul: ({ children }) => <ul className="mt-4 max-w-[68ch] list-disc space-y-2 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mt-4 max-w-[68ch] list-decimal space-y-2 pl-5">{children}</ol>,
  li: ({ children }) => <li className="font-serif text-[17px] leading-8 text-foreground">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ href, children }) => {
    if (href?.startsWith("#ref-")) {
      return (
        <sup className="ml-0.5 font-mono text-[10px] text-success">
          <a href={href} className="hover:underline">
            {children}
          </a>
        </sup>
      );
    }
    return (
      <a
        href={href}
        className="break-all text-success underline decoration-border underline-offset-4"
      >
        {children}
      </a>
    );
  },
};

export function ReportView({ markdown }: { markdown: string }) {
  const split = markdown.search(/^## References\s*$/m);
  const body = split === -1 ? markdown : markdown.slice(0, split);
  const listed = split === -1 ? [] : references(markdown.slice(split));

  return (
    <article className="mt-10 border-t border-border pt-10">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {citeLinks(body)}
      </ReactMarkdown>
      {listed.length > 0 ? (
        <>
          <h4 className="mt-12 font-serif text-3xl leading-tight text-foreground">References</h4>
          <div className="mt-6 grid gap-x-10 gap-y-4 md:grid-cols-2">
            {listed.map((item) => (
              <p key={item.number} id={`ref-${item.number}`} className="flex gap-3 text-sm leading-6">
                <span className="w-6 shrink-0 font-mono text-success">{item.number}</span>
                <a href={item.url} className="min-w-0 text-muted-foreground hover:text-foreground">
                  <span className="block text-foreground">{item.title || host(item.url)}</span>
                  <span className="block break-all">{item.url}</span>
                </a>
              </p>
            ))}
          </div>
        </>
      ) : null}
    </article>
  );
}
