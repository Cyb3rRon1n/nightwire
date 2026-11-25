"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { StateView } from "@/lib/nightwire/protocol";
import { serverUrl } from "@/lib/nightwire/media";

type LastNight = NonNullable<StateView["last_night"]>;

// Spec 2026-11-24-last-night-recap-design.md: last night's recap panels, opened only from the Status chip (owner's
// pick: nothing opens by itself). Radix returns focus to the chip, its Trigger.
export function LastNightOverlay({ recap, trigger, onOpen }: { recap: LastNight; trigger: React.ReactNode; onOpen: () => void }) {
  return (
    <Dialog.Root onOpenChange={(open) => { if (open) onOpen(); }}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50" style={{ background: "rgba(7,8,11,.94)" }} />
        <Dialog.Content className="nw-play fixed inset-0 z-50 overflow-y-auto p-4 sm:p-6" style={{ background: "rgba(7,8,11,.97)" }}
          aria-describedby={undefined}>
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="nw-speaker" style={{ color: "var(--nw-cyan)" }}>Last night · Night {recap.night}</Dialog.Title>
            <Dialog.Close className="nw-chip">Close</Dialog.Close>
          </div>
          <ol className="nw-recap-grid">
            {recap.panels.map((p) => (
              <li key={p.n} className="nw-recap-panel">
                <div className="nw-recap-art">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.art ? <img src={serverUrl(p.art)} alt="" /> : <span aria-hidden="true" />}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.portrait && <img className="nw-recap-face" src={serverUrl(p.portrait)} alt={p.speaker ?? ""} />}
                </div>
                <div className="flex flex-col gap-1 p-2 text-sm">
                  <span className="nw-panel-heading">{p.caption}</span>
                  <p>{p.speaker ? <><strong>{p.speaker}:</strong> “{p.text}”</> : p.text}</p>
                  <small style={{ color: "#9aa3ad" }}>{p.action}</small>
                </div>
              </li>
            ))}
          </ol>
          {recap.open.length > 0 && (
            <section aria-label="Still open" className="mt-6">
              <h2 className="nw-panel-heading">Still open</h2>
              <ul className="flex flex-col gap-1 text-sm">{recap.open.map((o, i) => <li key={i}>◇ {o}</li>)}</ul>
            </section>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
