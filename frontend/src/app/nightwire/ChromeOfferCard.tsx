"use client";

import { chromeById } from "./chrome";

export function ChromeOfferCard({ chromeId, onAccept, onDecline }: {
  chromeId: string; onAccept: () => void; onDecline: () => void;
}) {
  const c = chromeById(chromeId);
  return (
    <div className="nw-roll-card" role="group" aria-label="Chrome offer">
      <p className="nw-text-muted text-xs">Chrome offered</p>
      <p className="font-semibold">{c?.name ?? chromeId}</p>
      {c && (
        <p className="text-sm">
          {c.effect} · −{c.humanity} humanity · {c.installments} installments
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <button type="button" className="nw-btn-primary" onClick={onAccept}>Accept</button>
        <button type="button" className="nw-btn-ghost" onClick={onDecline}>Decline</button>
      </div>
    </div>
  );
}
