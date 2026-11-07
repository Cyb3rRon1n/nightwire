const WS_BASE = process.env.NEXT_PUBLIC_NIGHTWIRE_WS_URL || "ws://localhost:8000"

export function mediaUrl(relativePath: string): string {
  return `${WS_BASE.replace(/^ws/, "http")}/media/${relativePath}`
}

// Files the game server serves at its root, like the approved place art.
export function serverUrl(path: string): string {
  return `${WS_BASE.replace(/^ws/, "http")}/${path}`
}
