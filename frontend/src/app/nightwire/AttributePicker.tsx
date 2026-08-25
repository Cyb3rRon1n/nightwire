"use client";

// Mirrors ruleset/attributes.py's Attribute enum and
// docs/superpowers/specs/2026-08-25-attribute-point-buy-design.md's
// numbers - same duplication pattern SkillPicker.tsx already uses for
// SKILLS/skillCap on a WebSocket-first backend with no REST endpoint
// for static ruleset content.
export interface AttributeInfo {
  name: string;
  label: string;
}

export const ATTRIBUTES: AttributeInfo[] = [
  { name: "body", label: "Body" },
  { name: "reflexes", label: "Reflexes" },
  { name: "tech", label: "Tech" },
  { name: "cool", label: "Cool" },
  { name: "intellect", label: "Intellect" },
  { name: "presence", label: "Presence" },
];

export const ATTRIBUTE_BASE_SCORE = 10;
export const ATTRIBUTE_BUDGET = 12;
export const ATTRIBUTE_MIN = 6;
export const ATTRIBUTE_MAX = 14;

// The role's primary attribute starts at +1 over base - mirrors
// server/dispatch.py's _starting_attributes exactly.
export function startingAttributes(primaryAttribute: string | null): Record<string, number> {
  const starting: Record<string, number> = {};
  for (const attr of ATTRIBUTES) {
    starting[attr.name] = attr.name === primaryAttribute ? ATTRIBUTE_BASE_SCORE + 1 : ATTRIBUTE_BASE_SCORE;
  }
  return starting;
}

export function AttributePicker({
  attributes,
  primaryAttribute,
  onIncrement,
  onDecrement,
}: {
  attributes: Record<string, number>;
  primaryAttribute: string | null;
  onIncrement: (attributeName: string) => void;
  onDecrement: (attributeName: string) => void;
}) {
  const starting = startingAttributes(primaryAttribute);
  const spent = ATTRIBUTES.reduce(
    (total, attr) => total + ((attributes[attr.name] ?? starting[attr.name]) - starting[attr.name]),
    0,
  );
  const remaining = ATTRIBUTE_BUDGET - spent;

  return (
    <div className="nw-hud flex flex-col gap-1 text-sm nw-text-body">
      <p className="nw-eyebrow">
        Attributes ({remaining} point{remaining === 1 ? "" : "s"} remaining)
      </p>
      {ATTRIBUTES.map((attr) => {
        const score = attributes[attr.name] ?? starting[attr.name];
        return (
          <div key={attr.name} className="flex items-center justify-between gap-2">
            <span>
              {attr.label} ({score}){attr.name === primaryAttribute ? " ★" : ""}
            </span>
            <div className="flex gap-1">
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onDecrement(attr.name)}
                disabled={score <= ATTRIBUTE_MIN}
              >
                −
              </button>
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onIncrement(attr.name)}
                disabled={score >= ATTRIBUTE_MAX || remaining <= 0}
              >
                +
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
