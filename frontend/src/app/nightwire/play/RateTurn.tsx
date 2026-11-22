import type { ClientMessage, RatingReason, StateView } from "@/lib/nightwire/protocol";

const REASONS: Array<[RatingReason, string]> = [
  ["repeats", "Repeats itself"], ["acted_for_me", "Acted for me"], ["dull", "Dull"],
  ["wrong_facts", "Got facts wrong"], ["too_long", "Too long"],
];

// 👍/👎 for the newest turn (spec 2026-11-22 liked turns). Developer mode shows it under every turn; players only see
// it as a calm-moment check-in, so it never interrupts the story.
export function RateTurn({ view, send, dev }: { view: StateView; send: (msg: ClientMessage) => void; dev: boolean }) {
  const rating = view.last_rating;
  const checkin = view.checkin && !rating;
  if (!view.can_rate || (!dev && !checkin && !rating)) return null;
  const rate = (like: boolean, reason: RatingReason | null = null) => send({ type: "rate_turn", like, reason });
  return (
    <div className="nw-rate" role="group" aria-label={checkin ? "Check-in" : "Rate this turn"}>
      {checkin && <span className="nw-rate-ask">Quick one, choom: how&apos;s the story treating you?</span>}
      <button type="button" className="nw-chip" aria-pressed={rating?.like === true} aria-label="Liked it" onClick={() => rate(true)}>👍</button>
      <button type="button" className="nw-chip" aria-pressed={rating?.like === false} aria-label="Didn't like it" onClick={() => rate(false)}>👎</button>
      {rating?.like === false && REASONS.map(([value, label]) => (
        <button key={value} type="button" className="nw-chip" aria-pressed={rating.reason === value} onClick={() => rate(false, value)}>{label}</button>
      ))}
      {checkin && <button type="button" className="nw-rate-skip" onClick={() => send({ type: "dismiss_checkin" })}>Not now</button>}
      {rating && !dev && <span className="nw-rate-ask">Thanks.</span>}
    </div>
  );
}
