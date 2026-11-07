// Session and player IDs as typed by people: "Friday Game" today and "friday game " tomorrow should be the same game,
// and "#" or "/" must not break the connection URL (dry run 2026-11-06).
export function normalizeId(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, "-");
}
