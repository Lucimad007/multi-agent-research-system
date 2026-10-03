import type { Metadata } from "next";
import { IBM_Plex_Mono, Outfit, Source_Serif_4 } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { cn } from "@/lib/utils";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

const plex = IBM_Plex_Mono({
  variable: "--font-plex",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source",
  subsets: ["latin"],
});

const themeScript = `(function(){try{var stored=localStorage.getItem("desk-theme");var theme=stored==="light"||stored==="dark"?stored:(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.dataset.theme=theme;document.documentElement.classList.toggle("dark",theme==="dark");}catch(e){}})();`;

export const metadata: Metadata = {
  title: "Research desk",
  description: "Ask a question. Five agents search, compare, and write a cited report.",
  openGraph: {
    title: "Research desk",
    description: "Ask a question. Five agents search, compare, and write a cited report.",
    images: ["/desk-field.jpg"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={cn("h-full antialiased", outfit.variable, plex.variable, sourceSerif.variable, "font-sans")}
    >
      <body className="min-h-full">
        <Script id="desk-theme" strategy="beforeInteractive">
          {themeScript}
        </Script>
        {children}
      </body>
    </html>
  );
}
