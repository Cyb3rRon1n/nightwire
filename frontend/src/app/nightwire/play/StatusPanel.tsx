import { useState } from "react";
import type { CharacterSheet, ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { CharacterSheetBody } from "../CharacterSheetOverlay";

export function StatusPanel({ view, playerId, send }: { view: StateView; playerId: string; send: (msg: ClientMessage) => void }) {
  const me = view.characters[playerId] as CharacterSheet;
  // Skipped the portrait when making the character? It can still be made here (the portrait question now only
  // appears right after joining). "Generating" clears when the next view arrives, with or without a portrait.
  const [requested, setRequested] = useState<StateView | null>(null);
  const generating = requested === view;
  return (
    // .nw-theme keeps the sheet's own (older) classes working inside the play screen.
    <aside aria-label="Status" className="nw-side nw-theme flex flex-col gap-4 p-4" style={{ background: "#0b0d11" }}>
      {!me.portrait_path && (
        <button type="button" className="nw-chip self-start" disabled={generating}
          onClick={() => { send({ type: "approve_character" }); setRequested(view); }}>
          {generating ? "Generating portrait…" : "Generate portrait"}
        </button>
      )}
      <CharacterSheetBody
        character={me}
        onAllocateSkill={(skill) => send({ type: "allocate_skill_points", skill, amount: 1 })}
        onAllocateAttribute={(attribute) => send({ type: "allocate_attribute_points", attribute, amount: 1 })}
        onRemoveChrome={(item) => send({ type: "remove_chrome", item })}
      />
      {view.here && (
        <p className="text-sm" aria-label="Here">
          <span className="nw-panel-heading">Here</span> {view.here.place}: {view.here.mood}{view.here.mark ? ` · ${view.here.mark}` : ""}
        </p>
      )}
      <section aria-label="Objectives">
        <h2 className="nw-panel-heading">Objectives</h2>
        {view.active_objectives.length === 0
          ? <p className="text-sm" style={{ color: "#9aa3ad" }}>None yet.</p>
          : <ul className="flex flex-col gap-1 text-sm">{view.active_objectives.map((o) => <li key={o}>◆ {o}</li>)}</ul>}
      </section>
      <section aria-label="Promises">
        <h2 className="nw-panel-heading">Promises</h2>
        {(view.promises ?? []).length === 0
          ? <p className="text-sm" style={{ color: "#9aa3ad" }}>None open.</p>
          : <ul className="flex flex-col gap-1 text-sm">{[...view.promises].reverse().map((p) => (
              <li key={p.who + p.what}>◇ <strong>{p.who}</strong>: {p.what} <span style={{ color: "#9aa3ad" }}>· {ago(p.ago)}</span></li>
            ))}</ul>}
      </section>
      {(view.people ?? []).length > 0 && (
        <section aria-label="People">
          <h2 className="nw-panel-heading">People</h2>
          <ul className="flex flex-col gap-1 text-sm">{view.people.map((p) => (
            <li key={p.name}>
              <strong>{p.name}</strong>, {p.who} <span style={{ color: "#9aa3ad" }}>· {p.place ? `${p.place} · ` : ""}{ago(p.ago)}</span>
              <div style={{ color: "#9aa3ad" }}>{p.what}</div>
            </li>
          ))}</ul>
        </section>
      )}
      {(view.street ?? []).length > 0 && (
        <section aria-label="Word on the street">
          <h2 className="nw-panel-heading">Word on the street</h2>
          <ul className="flex flex-col gap-1 text-sm">{view.street.map((w) => (
            <li key={w.district}>
              <strong>{w.district}</strong>
              {w.good && <div>▲ {w.good}</div>}
              {w.bad && <div>▼ {w.bad}</div>}
            </li>
          ))}</ul>
        </section>
      )}
      {(view.journal ?? []).length > 0 && (
        <details>
          <summary className="nw-panel-heading cursor-pointer">Journal ({view.journal.length})</summary>
          <ul className="mt-2 flex flex-col gap-1 text-sm">{view.journal.map((j, i) => (
            <li key={i}><span style={{ color: "#9aa3ad" }}>{j.kind}</span> · {j.text} <span style={{ color: "#9aa3ad" }}>· {ago(j.ago)}</span></li>
          ))}</ul>
        </details>
      )}
    </aside>
  );
}

function ago(turns: number): string {
  return turns === 0 ? "this turn" : turns === 1 ? "1 turn ago" : `${turns} turns ago`;
}
