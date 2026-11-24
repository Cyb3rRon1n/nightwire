import { useState } from "react";
import type { StateView } from "@/lib/nightwire/protocol";
import { browserStore, readFlag, writeFlag } from "@/lib/nightwire/safeStorage";
import { CityMap } from "./CityMap";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";

const MAP_KEY = "nightwire-map-open";

export function WorldPanel({ view, playerId, onGo }: { view: StateView; playerId: string; onGo: (text: string) => void }) {
  const [mapOpen, setMapOpen] = useState(() => readFlag(browserStore, MAP_KEY, true));
  return (
    <aside aria-label="World" className="nw-side flex flex-col gap-4 p-4">
      {view.map && (
        <details open={mapOpen} onToggle={(e) => {
          const open = e.currentTarget.open;
          writeFlag(browserStore, MAP_KEY, open);
          setMapOpen(open);
        }}>
          <summary className="nw-panel-heading cursor-pointer">Map</summary>
          <CityMap map={view.map} onGo={onGo} />
        </details>
      )}
      <section aria-label="Scene">
        <h2 className="nw-panel-heading">Scene</h2>
        <p className="text-sm">{view.location ?? "Kuroshio"}{view.scene_mood ? ` · ${view.scene_mood}` : ""}</p>
        {view.in_combat && (
          <p className="nw-hud text-xs" style={{ color: "#ff8a80" }}>
            IN COMBAT{view.current_turn ? ` · ${view.current_turn}'S TURN` : ""}
          </p>
        )}
      </section>
      <section aria-label="Party">
        <h2 className="nw-panel-heading">Party</h2>
        <ul className="flex flex-col gap-2">
          {Object.entries(view.characters).map(([id, c]) => {
            const portrait = "portrait_path" in c ? c.portrait_path : null;
            const { initials, colorClass } = portraitFor(c.role, c.name);
            return (
              <li key={id} className="flex items-center gap-2 text-sm" style={id === playerId ? { color: "var(--nw-cyan)" } : undefined}>
                {portrait ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={mediaUrl(portrait)} alt="" className="size-8 object-cover" style={{ border: "1.5px solid var(--nw-frame-cool)" }} />
                ) : (
                  <span className={`flex size-8 items-center justify-center text-xs font-semibold ${colorClass}`}>{initials}</span>
                )}
                <span>
                  {c.name} · {c.health}/{c.max_health} HP{c.armor > 0 ? ` · ${c.armor} armor` : ""}
                  {c.conditions.length ? ` · ${c.conditions.join(", ")}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
