import { spawn } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const query = typeof body?.query === "string" ? body.query.trim() : "";
  if (!query || query.length > 500) {
    return Response.json({ error: "Enter a research question." }, { status: 400 });
  }

  const root = path.resolve(process.cwd(), "../..");
  const child = spawn("uv", ["run", "python", "scripts/run_research.py"], {
    cwd: root,
    env: { ...process.env, RESEARCH_QUERY: query, PYTHONIOENCODING: "utf-8" },
  });

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      const send = (chunk: Buffer | string) => {
        controller.enqueue(encoder.encode(typeof chunk === "string" ? chunk : chunk.toString()));
      };
      child.stdout.on("data", send);
      child.stderr.on("data", send);
      child.on("error", (error) => {
        send(`\n__RESULT__${JSON.stringify({ error: error.message, answer: null, handoffs: [] })}`);
        controller.close();
      });
      child.on("close", () => controller.close());
    },
    cancel() {
      child.kill();
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
