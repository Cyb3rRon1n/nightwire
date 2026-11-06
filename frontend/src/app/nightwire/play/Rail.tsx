export function Rail({ label, side, onOpen, badge }: { label: string; side: "left" | "right"; onOpen: () => void; badge?: number }) {
  return (
    <button type="button" onClick={onOpen} aria-label={`Open ${label} panel`} className="nw-rail">
      <span aria-hidden="true">{side === "left" ? "›" : "‹"}</span>
      <span className="nw-rail-label">{label}</span>
      {badge ? <span className="nw-rail-badge">{badge}</span> : null}
    </button>
  );
}
