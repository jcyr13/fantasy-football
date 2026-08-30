// The wrapping annotation cell used by the Waiver/FA and Trade Desk tables:
// the backend's per-row `reasons` as a compact stacked list, em-dash when empty.

export function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return <span className="faint">—</span>;
  }
  return (
    <ul className="reasons">
      {reasons.map((r, i) => (
        <li key={i}>{r}</li>
      ))}
    </ul>
  );
}
