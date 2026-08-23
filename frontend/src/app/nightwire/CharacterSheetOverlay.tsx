import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
import type { CharacterSheet } from "@/lib/nightwire/protocol";

export function CharacterSheetOverlay({
  character,
  onClose,
}: {
  character: CharacterSheet;
  onClose: () => void;
}) {
  const { initials, colorClass } = portraitFor(character.role, character.name);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-stone-800 bg-stone-950 p-5 text-stone-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-stone-800 pb-3">
          {character.portrait_path ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaUrl(character.portrait_path)} alt="" className="size-10 rounded-lg object-cover" />
          ) : (
            <span className={`flex size-10 items-center justify-center rounded-lg text-sm font-semibold ${colorClass}`}>
              {initials}
            </span>
          )}
          <div>
            <p className="font-semibold">{character.name}</p>
            <p className="text-xs text-stone-500">
              {character.role} · {character.lifepath}
            </p>
          </div>
        </div>

        <div className="border-b border-stone-800 py-3">
          <p className="mb-1 text-xs uppercase tracking-wide text-stone-500">Attributes</p>
          {Object.keys(character.attributes).length === 0 ? (
            <p className="text-sm text-stone-500">None set.</p>
          ) : (
            <div className="grid grid-cols-3 gap-1 text-sm">
              {Object.entries(character.attributes).map(([attr, value]) => (
                <span key={attr}>
                  {attr}: {value}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="border-b border-stone-800 py-3 text-sm">
          <p className="mb-1 text-xs uppercase tracking-wide text-stone-500">Condition</p>
          <p>
            {character.health}/{character.max_health} HP · {character.armor} armor
          </p>
          {character.conditions.length > 0 && (
            <p className="text-stone-400">{character.conditions.join(", ")}</p>
          )}
        </div>

        <div className="pt-3">
          <p className="mb-1 text-xs uppercase tracking-wide text-stone-500">Inventory</p>
          {character.inventory.length === 0 ? (
            <p className="text-sm text-stone-500">Empty.</p>
          ) : (
            <p className="text-sm">{character.inventory.join(", ")}</p>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          className="mt-4 w-full rounded bg-stone-900 px-3 py-2 text-sm text-stone-300 hover:bg-stone-800"
        >
          Close (Ctrl+K)
        </button>
      </div>
    </div>
  );
}
