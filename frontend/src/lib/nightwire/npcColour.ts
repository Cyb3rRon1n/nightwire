import { NPC_PALETTES, NPC_SLUGS } from "./npcPalettes.ts";

export const GOLD = "#f9d066";
// 86% ink over pure white: the brightest background the scene scrim lets text sit on.
export const WORST_BG = "#2a2b2d";

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const chroma = (hex: string) => Math.max(...rgb(hex)) - Math.min(...rgb(hex));

function towardWhite(hex: string, t: number): string {
  return "#" + rgb(hex).map((c) => Math.round((c + (1 - c) * t) * 255).toString(16).padStart(2, "0")).join("");
}

// The palette's most vivid colour, lifted toward white until it is readable on the scrim.
// The approved design a speaker's name refers to: the full name, or a first or last name alone, any case.
function designName(name: string): string | null {
  const key = name.trim().toLowerCase();
  return Object.keys(NPC_PALETTES).find((full) => {
    const f = full.toLowerCase();
    return f === key || f.split(" ").includes(key);
  }) ?? null;
}

// Path of the NPC's approved portrait on the game server, or null for someone without a design.
export function npcPortrait(name: string): string | null {
  const full = designName(name);
  return full && NPC_SLUGS[full] ? `character-art/${NPC_SLUGS[full]}.jpg` : null;
}

export function npcColour(name: string): string {
  const full = designName(name);
  const vivid = (full ? NPC_PALETTES[full] : undefined)?.filter((c) => chroma(c) >= 0.25).sort((a, b) => chroma(b) - chroma(a))[0];
  if (!vivid) return GOLD;
  for (let t = 0; t <= 1; t += 0.05) {
    const c = towardWhite(vivid, t);
    if (contrast(c, WORST_BG) >= 4.5) return c;
  }
  return "#ffffff";
}
