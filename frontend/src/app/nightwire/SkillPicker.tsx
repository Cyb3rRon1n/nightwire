"use client";

// Mirrors ruleset/skills.py's SKILLS dict and skill_cap() - same
// duplication pattern page.tsx's own ROLES/LIFEPATHS constants already
// use for this exact kind of static ruleset content, rather than a new
// REST endpoint on a WebSocket-first backend.
export interface SkillInfo {
  name: string;
  label: string;
  governingAttribute: string;
  description: string;
}

export const SKILLS: SkillInfo[] = [
  { name: "melee", label: "Melee", governingAttribute: "body", description: "Close-quarters combat with blades, fists, or improvised weapons." },
  { name: "athletics", label: "Athletics", governingAttribute: "body", description: "Running, climbing, jumping, and other raw physical feats." },
  { name: "ranged_combat", label: "Ranged Combat", governingAttribute: "reflexes", description: "Firearms and thrown weapons at range." },
  { name: "stealth", label: "Stealth", governingAttribute: "reflexes", description: "Moving unseen, staying quiet, avoiding detection." },
  { name: "piloting", label: "Piloting", governingAttribute: "reflexes", description: "Driving or flying vehicles, high-speed maneuvers." },
  { name: "hacking", label: "Hacking", governingAttribute: "tech", description: "Breaching networks, bypassing security software, digital intrusion." },
  { name: "engineering", label: "Engineering", governingAttribute: "tech", description: "Building, repairing, and modifying gear and cyberware." },
  { name: "demolitions", label: "Demolitions", governingAttribute: "tech", description: "Explosives - rigging, defusing, controlled destruction." },
  { name: "intimidation", label: "Intimidation", governingAttribute: "cool", description: "Coercion through threat, presence, or reputation." },
  { name: "streetwise", label: "Streetwise", governingAttribute: "cool", description: "Reading the street - contacts, black markets, gang politics." },
  { name: "perception", label: "Perception", governingAttribute: "intellect", description: "Noticing details, spotting danger, reading a scene." },
  { name: "deduction", label: "Deduction", governingAttribute: "intellect", description: "Piecing together clues, drawing logical conclusions." },
  { name: "persuasion", label: "Persuasion", governingAttribute: "presence", description: "Convincing others through charm, logic, or negotiation." },
  { name: "performance", label: "Performance", governingAttribute: "presence", description: "Holding a crowd - music, acting, showmanship." },
];

// Mirrors ruleset/skills.py's skill_cap(): min(5, modifier(score) + 3).
export function skillCap(attributeScore: number): number {
  const modifier = Math.floor((attributeScore - 10) / 2);
  return Math.min(5, modifier + 3);
}

// Two call sites share this: the pre-join creation picker (onDecrement
// present - it's just adjusting a local draft, nothing's committed until
// Join is sent) and the post-join milestone spend (onDecrement omitted -
// spend-only, no mechanism to move already-committed points, per spec).
export function SkillPicker({
  skills,
  attributes,
  remaining,
  onIncrement,
  onDecrement,
}: {
  skills: Record<string, number>;
  attributes: Record<string, number>;
  remaining: number;
  onIncrement: (skillName: string) => void;
  onDecrement?: (skillName: string) => void;
}) {
  return (
    <div className="nw-hud flex flex-col gap-1 text-sm nw-text-body">
      <p className="nw-eyebrow">
        Skills ({remaining} point{remaining === 1 ? "" : "s"} remaining)
      </p>
      {SKILLS.map((skill) => {
        const rank = skills[skill.name] ?? 0;
        const cap = skillCap(attributes[skill.governingAttribute] ?? 10);
        return (
          <div key={skill.name} className="flex items-center justify-between gap-2">
            <span title={skill.description}>
              {skill.label} ({rank}/{cap})
            </span>
            <div className="flex gap-1">
              {onDecrement && (
                <button
                  type="button"
                  className="nw-btn-ghost"
                  onClick={() => onDecrement(skill.name)}
                  disabled={rank === 0}
                >
                  −
                </button>
              )}
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onIncrement(skill.name)}
                disabled={rank >= cap || remaining <= 0}
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
