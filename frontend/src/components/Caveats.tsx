// The shared "Methodology & confidence" panel. Every screen's response carries
// the assembly's `caveats` — the v1 approximations it had to make where the
// pulls were too thin for a layer's real input (ADR-0013 §4, §6). Renders
// nothing when the list is empty.

export function Caveats({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="panel">
      <h2>Methodology &amp; confidence</h2>
      <ul className="caveats">
        {items.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </div>
  );
}
