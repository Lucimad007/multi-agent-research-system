"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";

export function Header() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const next = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    setTheme(next);
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    document.documentElement.classList.toggle("dark", next === "dark");
    localStorage.setItem("desk-theme", next);
    setTheme(next);
  }

  return (
    <header className="fixed inset-x-0 top-4 z-40 px-4">
      <nav className="glass-nav mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 rounded-full px-4 sm:px-5">
        <a href="#desk" className="hidden text-sm font-medium tracking-tight text-[var(--ink)] sm:inline">
          Research desk
        </a>
        <div className="flex items-center gap-4 text-sm whitespace-nowrap text-[var(--muted)] sm:gap-6">
          <a href="#desk" className="text-[var(--ink)]">
            Question
          </a>
          <a href="#method" className="hover:text-[var(--ink)]">
            Progress
          </a>
          <a href="#report" className="hover:text-[var(--ink)]">
            Report
          </a>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={toggleTheme}
            aria-pressed={theme === "light"}
            className="rounded-full"
          >
            {theme === "dark" ? "Light" : "Dark"}
          </Button>
        </div>
      </nav>
    </header>
  );
}
