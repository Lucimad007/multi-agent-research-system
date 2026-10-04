import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

/** Adapted from the 21st.dev Hero Section Dark grid. Line color follows the desk tokens. */
export function RetroGrid({ className }: { className?: string }) {
  return (
    <div
      className={cn("pointer-events-none absolute inset-0 overflow-hidden opacity-40", className)}
      style={{ "--cell-size": "56px" } as CSSProperties}
      aria-hidden="true"
    >
      <div className="absolute inset-0 [perspective:180px]">
        <div className="absolute inset-0 [transform:rotateX(58deg)]">
          <div className="animate-grid absolute inset-x-[-100%] top-0 h-[280%] bg-[linear-gradient(to_right,var(--line)_1px,transparent_1px),linear-gradient(to_bottom,var(--line)_1px,transparent_1px)] bg-[size:var(--cell-size)_var(--cell-size)]" />
        </div>
      </div>
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background" />
    </div>
  );
}
