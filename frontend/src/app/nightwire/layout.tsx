import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nightwire",
  description: "A cyberpunk tabletop RPG with an AI game master.",
};

export default function NightwireLayout({ children }: { children: React.ReactNode }) {
  return children;
}
