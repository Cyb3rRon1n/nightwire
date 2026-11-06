import type { CharacterSheet, ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { CharacterSheetBody } from "../CharacterSheetOverlay";

export function StatusPanel({ view, playerId, send }: { view: StateView; playerId: string; send: (msg: ClientMessage) => void }) {
  const me = view.characters[playerId] as CharacterSheet;
  return (
    // .nw-theme keeps the sheet's own (older) classes working inside the play screen.
    <aside aria-label="Status" className="nw-side nw-theme flex flex-col gap-4 p-4" style={{ background: "#0b0d11" }}>
      <CharacterSheetBody
        character={me}
        onAllocateSkill={(skill) => send({ type: "allocate_skill_points", skill, amount: 1 })}
        onAllocateAttribute={(attribute) => send({ type: "allocate_attribute_points", attribute, amount: 1 })}
        onRemoveChrome={(item) => send({ type: "remove_chrome", item })}
      />
      <section aria-label="Objectives">
        <h2 className="nw-panel-heading">Objectives</h2>
        {view.active_objectives.length === 0
          ? <p className="text-sm" style={{ color: "#9aa3ad" }}>None yet.</p>
          : <ul className="flex flex-col gap-1 text-sm">{view.active_objectives.map((o) => <li key={o}>◆ {o}</li>)}</ul>}
      </section>
    </aside>
  );
}
