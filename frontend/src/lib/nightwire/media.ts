const WS_BASE = process.env.NEXT_PUBLIC_NIGHTWIRE_WS_URL || "ws://localhost:8000"

export function mediaUrl(relativePath: string): string {
  return `${WS_BASE.replace(/^ws/, "http")}/media/${relativePath}`
}
