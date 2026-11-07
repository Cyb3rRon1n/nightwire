"use client";

import { useEffect, useRef, useState } from "react";
import type { ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { serverUrl } from "@/lib/nightwire/media";
import { sortedContacts, trustLabel } from "@/lib/nightwire/phone";

// The phone body: contact chips, thread, typing line, private text input.
// Floating on wide screens (PlayScreen wraps it), inline in the PHONE tab on narrow ones.
export function PhonePanel({ view, send, onClose }: { view: StateView; send: (msg: ClientMessage) => void; onClose?: () => void }) {
  const contacts = sortedContacts(view);
  const [picked, setPicked] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const selected = contacts.find((c) => c.name === picked) ?? contacts[0] ?? null;
  const name = selected?.name ?? null;
  const unread = selected?.unread ?? 0;
  const thread = (name && view.phone.threads[name]) || [];
  const typing = !!name && view.phone.typing.includes(name);
  const endRef = useRef<HTMLDivElement>(null);

  // Mark read when the thread is open and has unread; the server clears unread, so this cannot loop.
  useEffect(() => {
    if (name && unread > 0) send({ type: "read", contact: name });
  }, [name, unread, send]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [name, thread.length, typing]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!name || !text) return;
    send({ type: "text", to: name, text });
    setDraft("");
  }

  return (
    <section aria-label="Phone" className="nw-phone-body">
      <div className="nw-phone-top">
        <span className="nw-panel-heading" style={{ margin: 0 }}>Phone</span>
        {onClose && <button type="button" className="nw-phone-x" aria-label="Close phone" onClick={onClose}>×</button>}
      </div>
      {contacts.length === 0 ? (
        <p className="nw-phone-empty">No contacts yet. Meet someone first.</p>
      ) : (
        <>
          <div className="nw-phone-chips" role="tablist" aria-label="Contacts">
            {contacts.map((c) => (
              <button key={c.name} type="button" role="tab" aria-selected={c.name === name} className="nw-phone-chip"
                aria-label={c.unread > 0 ? `${c.name}, ${c.unread} unread` : c.name} onClick={() => setPicked(c.name)}>
                {c.portrait
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={serverUrl(c.portrait)} alt="" />
                  : <span className="nw-phone-initial" aria-hidden="true">{c.name.charAt(0)}</span>}
                <span>{c.name}</span>
                {c.unread > 0 && <i className="nw-phone-dot" aria-hidden="true" />}
              </button>
            ))}
          </div>
          {selected && <p className="nw-phone-meta">{selected.role} · {trustLabel(selected.trust)}</p>}
          <div className="nw-phone-thread" role="log" aria-label={`Texts with ${name}`}>
            {thread.map((m, i) => (
              <p key={i} className={m.sender === "me" ? "nw-bubble nw-bubble-me" : "nw-bubble"}>{m.text}</p>
            ))}
            {typing && <p className="nw-phone-typing" role="status">{name} is typing…</p>}
            <div ref={endRef} />
          </div>
          <form className="nw-phone-form" onSubmit={submit}>
            <input aria-label={`Text ${name}`} placeholder={`Text ${name}`} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <button type="submit" className="nw-send" disabled={!draft.trim()}>Send</button>
          </form>
        </>
      )}
    </section>
  );
}
