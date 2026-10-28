// Hand-checked mirror of ruleset/cyberware.py (same pattern as ROLES / SkillPicker).
export interface ChromeInfo { id: string; name: string; effect: string; humanity: number; installments: number }

export const CHROME: ChromeInfo[] = [
  { id: "hawkeye_optics", name: "Hawkeye optics", effect: "+1 Perception", humanity: 3, installments: 2 },
  { id: "reflex_wires", name: "Reflex wires", effect: "+1 Ranged combat", humanity: 6, installments: 3 },
  { id: "kagerou", name: "Kagerou", effect: "⚡ Overclock: roll twice, keep higher, +2", humanity: 10, installments: 5 },
  { id: "kama_blades", name: "Kama blades", effect: "+2 Melee", humanity: 8, installments: 4 },
  { id: "oni_arms", name: "Oni arms", effect: "+1 Melee, +1 Athletics", humanity: 7, installments: 4 },
  { id: "lacquer_skin", name: "Lacquer skin", effect: "+10 Armor", humanity: 6, installments: 3 },
  { id: "yomi_jack", name: "Yomi jack", effect: "+1 Hacking; ⚡ Overclock +3 on hacking", humanity: 5, installments: 3 },
  { id: "pain_editor", name: "Pain editor", effect: "+15 Max health", humanity: 5, installments: 3 },
  { id: "silk_tongue", name: "Silk tongue", effect: "+1 Persuasion", humanity: 3, installments: 2 },
  { id: "kumo_hand", name: "Kumo hand", effect: "+1 Engineering", humanity: 3, installments: 2 },
  { id: "neon_ink", name: "Neon ink", effect: "Fashionware (style only)", humanity: 0, installments: 1 },
];

export const chromeById = (id: string) => CHROME.find((c) => c.id === id);

export function humanityTier(h: number): string {
  return h >= 70 ? "Steady" : h >= 40 ? "Frayed" : h >= 20 ? "Slipping" : h >= 1 ? "Edge" : "Gone too far";
}
