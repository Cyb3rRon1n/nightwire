"use client";

import { useEffect, useState } from "react";
import type { PendingRoll, RollResult } from "@/lib/nightwire/protocol";

const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const sign = (n: number) => (n >= 0 ? `+${n}` : `${n}`);
const OUTCOME = {
  clean_success: { text: "Clean success", cls: "nw-roll-success" },
  complication: { text: "Complication", cls: "nw-roll-complication" },
  failure: { text: "Failure", cls: "nw-roll-failure" },
} as const;

export function PendingRollCard({ roll, isMine, onRoll, rolling }: {
  roll: PendingRoll; isMine: boolean; onRoll: (overclock?: string) => void; rolling: boolean;
}) {
  return (
    <div className="nw-roll-card" role="group" aria-label={`Roll for ${roll.name}`}>
      <p className="nw-text-muted text-xs">{roll.reason}</p>
      <p className="font-semibold">
        {label(roll.skill)} ({label(roll.attribute)}) · {label(roll.difficulty)} {roll.dc}
      </p>
      {isMine ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className="nw-btn-primary" onClick={() => onRoll()} disabled={rolling}>
            {rolling ? "Rolling…" : "Roll"}
          </button>
          {(roll.overclocks ?? []).map((o) => (
            <button key={o.id} type="button" className="nw-btn-ghost" onClick={() => onRoll(o.id)} disabled={rolling}>
              ⚡ Overclock ({o.name}) · {o.bonus_text} · −1d6 humanity
            </button>
          ))}
        </div>
      ) : (
        <p className="nw-text-faint mt-2 text-xs">Waiting for {roll.name} to roll…</p>
      )}
    </div>
  );
}

export function RollResultCard({ roll, animate }: { roll: RollResult; animate: boolean }) {
  const [landed, setLanded] = useState(!animate);
  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setLanded(true), 700);
    return () => clearTimeout(t);
  }, [animate]);
  const total = roll.die_result + roll.attribute_mod + roll.skill_mod + (roll.overclock_bonus ?? 0);
  const natural = roll.die_result === 10 || roll.die_result === 1;
  const outcome = OUTCOME[roll.outcome] ?? OUTCOME.failure;
  return (
    <div className={`nw-roll-card ${landed && natural ? "nw-roll-natural" : ""}`}>
      <p className="nw-text-muted text-xs">{roll.name} · {label(roll.skill)} vs {label(roll.difficulty)} {roll.dc}</p>
      <div className="flex items-center gap-3">
        <span className={`nw-d10 ${landed ? "" : "nw-d10-tumble"}`} aria-hidden={!landed}>
          {landed ? roll.die_result : "?"}
        </span>
        {landed && (
          <>
            <span className="text-sm">
              {roll.second_die !== undefined && `⚡ ${roll.first_die} / ${roll.second_die} → `}{roll.die_result} {sign(roll.attribute_mod)} {label(roll.attribute)} {sign(roll.skill_mod)} {label(roll.skill)}{roll.overclock_bonus ? ` ${sign(roll.overclock_bonus)} ⚡` : ""} = {total} vs {roll.dc}
            </span>
            <span role="status" className={`nw-roll-badge ${outcome.cls}`}>{outcome.text}{natural ? ` · natural ${roll.die_result}` : ""}</span>
            {roll.humanity_loss ? <span className="nw-text-muted text-xs">−{roll.humanity_loss} humanity</span> : null}
          </>
        )}
      </div>
    </div>
  );
}
