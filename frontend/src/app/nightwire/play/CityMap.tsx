import { useState } from "react";
import type { MapDistrict, StateView } from "@/lib/nightwire/protocol";
import { serverUrl } from "@/lib/nightwire/media";

// Spec 2026-11-24-district-map-design.md: a Beck-style diagram (topology, not geography) in a 300×320 box.
// The Ring Line train is the inner ring, the Loop expressway the outer one; the lines are decoration only, and every
// district is a real button on top, so the map works from the keyboard and reads as a list.
const AT: Record<string, [number, number]> = {
  "Tenjō Heights": [150, 22], "Hanabira-chō": [150, 96], "Ikebe Low": [234, 166], "Kuroshio Docks": [150, 236],
  "Ring Line": [66, 166], "The Loop": [246, 298], "Yomi Line": [54, 298],
};
const RING = "110,96 190,96 234,140 234,192 190,236 110,236 66,192 66,140";
const LOOP = "100,66 200,66 264,130 264,202 200,266 100,266 36,202 36,130";

const pips = (c: { filled: number; size: number }) =>
  Array.from({ length: c.size }, (_, i) => (i < c.filled ? "●" : "○")).join("");

// The one state mark a district gets beside "you are here": its pressure clock once it moves, else a mood that isn't calm.
function mark(d: MapDistrict): string {
  if (d.clock && d.clock.filled > 0) return pips(d.clock);
  return d.mood === "calm" ? "" : d.mood;
}

export function CityMap({ map, onGo }: { map: NonNullable<StateView["map"]>; onGo: (text: string) => void }) {
  const [picked, setPicked] = useState<string | null>(null);
  const shown = map.districts.find((d) => d.name === picked) ?? map.districts.find((d) => d.here) ?? null;
  return (
    <figure className="nw-map">
      <div className="nw-map-diagram">
        <svg viewBox="0 0 300 320" aria-hidden="true">
          <polygon points={LOOP} className="nw-map-loop" />
          <polyline points="200,266 230,298 246,298" className="nw-map-loop-ramp" />
          <polygon points={RING} className="nw-map-ring" />
          <line x1="150" y1="96" x2="150" y2="22" className="nw-map-spur" />
          <text x="156" y="50" className="nw-map-note">maglev · sponsor badge</text>
          <line x1="14" y1="298" x2="120" y2="298" className="nw-map-sealed" />
          <text x="18" y="316" className="nw-map-note">sealed</text>
        </svg>
        {map.districts.map((d) => {
          const [x, y] = AT[d.name] ?? [150, 160];
          const m = mark(d);
          return (
            <button key={d.name} type="button" className="nw-map-stop" data-here={d.here || undefined}
              aria-current={d.here ? "location" : undefined} aria-pressed={shown?.name === d.name}
              style={{ left: `${(x / 300) * 100}%`, top: `${(y / 320) * 100}%` }}
              onClick={() => setPicked(d.name)}>
              <span>{d.here && <b className="nw-map-you">YOU </b>}{d.name}</span>
              {m && <small>{m}</small>}
            </button>
          );
        })}
      </div>
      <figcaption className="text-xs" style={{ color: "#9aa3ad" }}>{map.caption}</figcaption>
      {shown && (
        <section aria-label={`${shown.name} card`} className="nw-map-card">
          {shown.art && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={serverUrl(shown.art)} alt="" />
          )}
          <div className="flex flex-col gap-1 text-sm">
            <strong>{shown.name} <span style={{ color: "#9aa3ad" }}>· {shown.mood}</span></strong>
            {shown.clock && (
              <span role="img" aria-label={`Pressure ${shown.clock.filled} of ${shown.clock.size}`}>Pressure {pips(shown.clock)}</span>
            )}
            {shown.people.length > 0 && <span>People: {shown.people.join(", ")}</span>}
            {shown.places.length > 0 && <span>Places: {shown.places.join(", ")}</span>}
            {shown.go
              ? <button type="button" className="nw-chip self-start" onClick={() => onGo(shown.go as string)}>Go</button>
              : <span style={{ color: "var(--nw-cyan)" }}>You are here</span>}
          </div>
        </section>
      )}
    </figure>
  );
}
