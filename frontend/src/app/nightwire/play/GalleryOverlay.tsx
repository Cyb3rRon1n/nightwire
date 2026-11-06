"use client";

import { useRef } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { mediaUrl } from "@/lib/nightwire/media";

// The session's scene images, newest first. Radix gives Escape-to-close and
// the focus trap; it only returns focus to its own Trigger, and this opens from
// the header button or a feed image, so the opener is remembered here.
export function GalleryOverlay({ images, openIndex, onClose }: { images: string[]; openIndex: number | null; onClose: () => void }) {
  const opener = useRef<HTMLElement | null>(null);
  const newestFirst = images.map((src, i) => ({ src, i })).reverse();
  return (
    <Dialog.Root open={openIndex !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50" style={{ background: "rgba(7,8,11,.94)" }} />
        <Dialog.Content className="nw-play fixed inset-0 z-50 overflow-y-auto p-4 sm:p-6" style={{ background: "rgba(7,8,11,.97)" }} aria-describedby={undefined}
          onOpenAutoFocus={() => { opener.current = document.activeElement as HTMLElement | null; }}
          onCloseAutoFocus={(e) => { e.preventDefault(); opener.current?.focus(); }}
        >
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="nw-speaker" style={{ color: "var(--nw-cyan)" }}>Gallery · {images.length}</Dialog.Title>
            <Dialog.Close className="nw-chip">Close</Dialog.Close>
          </div>
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 360px), 1fr))" }}>
            {newestFirst.map(({ src, i }) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={mediaUrl(src)}
                alt={`Scene image ${i + 1}`}
                className="w-full"
                style={{ border: `1.5px solid ${i === openIndex ? "var(--nw-cyan)" : "var(--nw-frame-cool)"}` }}
                ref={i === openIndex ? (el) => el?.scrollIntoView({ block: "center" }) : undefined}
              />
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
