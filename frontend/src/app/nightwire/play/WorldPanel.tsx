import type { StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";

export function WorldPanel({ view, playerId }: { view: StateView; playerId: string }) {
  return (
    <aside aria-label="World" className="nw-side flex flex-col gap-4 p-4">
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
