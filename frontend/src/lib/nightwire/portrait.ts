// Deliberately cheap placeholder avatar - initials + a color picked
// deterministically from role, not real art (that's Phase 5's job).
// Neon Noir palette (arbitrary values, not shared Tailwind theme tokens -
// see ../../app/nightwire/theme.css for why this stays route-local).
const PALETTE = [
  "bg-[#b967ff] text-[#0d0620]",
  "bg-[#00e5ff] text-[#0d0620]",
  "bg-[#ff4d6d] text-[#0d0620]",
  "bg-[#39ff88] text-[#0d0620]",
  "bg-[#ffb84d] text-[#0d0620]",
  "bg-[#4d8fff] text-[#0d0620]",
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

export function portraitFor(role: string, name: string): { initials: string; colorClass: string } {
  const initials = name.trim().slice(0, 2).toUpperCase() || "?"
  const colorClass = PALETTE[hashString(role) % PALETTE.length]
  return { initials, colorClass }
}
