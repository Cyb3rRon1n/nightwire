import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
import type { CharacterSheet } from "@/lib/nightwire/protocol";
import { SkillPicker } from "./SkillPicker";
import { AttributePicker, ATTRIBUTE_MILESTONE_MAX } from "./AttributePicker";
import "./theme.css";

export function CharacterSheetOverlay({
  character,
  onClose,
  onAllocateSkill,
  onAllocateAttribute,
}: {
  character: CharacterSheet;
  onClose: () => void;
  onAllocateSkill: (skill: string) => void;
  onAllocateAttribute: (attribute: string) => void;
}) {
  const { initials, colorClass } = portraitFor(character.role, character.name);

  return (
    <div
      className="nw-theme nw-sheet-backdrop fixed inset-0 z-50 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="nw-sheet-panel w-full max-w-sm rounded-xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="nw-divider flex items-center gap-3 border-b pb-3 mb-3">
          {character.portrait_path ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaUrl(character.portrait_path)} alt="" className="size-10 rounded-lg object-cover" />
          ) : (
            <span className={`flex size-10 items-center justify-center rounded-lg text-sm font-semibold ${colorClass}`}>
              {initials}
            </span>
          )}
          <div>
            <p className="nw-heading text-sm">{character.name}</p>
            <p className="nw-hud text-xs nw-text-muted">
              {character.role} · {character.lifepath}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="nw-sheet-box p-3">
            <p className="nw-eyebrow mb-1">
              Attributes
            </p>
            {character.unspent_attribute_points > 0 ? (
              <AttributePicker
                attributes={character.attributes}
                primaryAttribute={null}
                remaining={character.unspent_attribute_points}
                maxScore={ATTRIBUTE_MILESTONE_MAX}
                onIncrement={onAllocateAttribute}
              />
            ) : Object.keys(character.attributes).length === 0 ? (
              <p className="text-sm nw-text-faint">None set.</p>
            ) : (
              <div className="nw-hud grid grid-cols-3 gap-1 text-sm nw-text-body">
                {Object.entries(character.attributes).map(([attr, value]) => (
                  <span key={attr}>
                    {attr}: {value}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="nw-sheet-box p-3">
            <p className="nw-eyebrow mb-1">Skills</p>
            {character.unspent_skill_points > 0 ? (
              <SkillPicker
                skills={character.skills}
                attributes={character.attributes}
                remaining={character.unspent_skill_points}
                onIncrement={onAllocateSkill}
              />
            ) : Object.keys(character.skills).length === 0 ? (
              <p className="text-sm nw-text-faint">None trained.</p>
            ) : (
              <div className="nw-hud grid grid-cols-2 gap-1 text-sm nw-text-body">
                {Object.entries(character.skills).map(([skill, rank]) => (
                  <span key={skill}>
                    {skill}: {rank}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="nw-sheet-box nw-hud p-3 text-sm nw-text-body">
            <p className="nw-eyebrow mb-1">
              Condition
            </p>
            <p>
              {character.health}/{character.max_health} HP · {character.armor} armor
            </p>
            {character.conditions.length > 0 && (
              <p className="nw-text-muted">{character.conditions.join(", ")}</p>
            )}
          </div>

          <div className="nw-sheet-box nw-hud p-3 text-sm nw-text-body">
            <p className="nw-eyebrow mb-1">
              Inventory
            </p>
            {character.inventory.length === 0 ? (
              <p className="nw-text-faint">Empty.</p>
            ) : (
              <ul className="flex flex-col gap-0.5">
                {character.inventory.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <button type="button" onClick={onClose} className="nw-btn-ghost mt-4 w-full">
          Close (Ctrl+K)
        </button>
      </div>
    </div>
  );
}
