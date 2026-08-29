// The Dead Parrots wordmark: a parrot flat on its back, feet up — "this parrot
// is deceased". Stroke uses currentColor so the masthead controls the tint.

export function Logo() {
  return (
    <div className="logo">
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <line x1="5" y1="34" x2="43" y2="34" strokeLinecap="round" />
        <ellipse cx="25" cy="26" rx="13" ry="6" />
        <circle cx="12" cy="24" r="4" />
        <path d="M8 23 L3 24 L8 25" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M38 26 L46 22 M38 27 L46 30" strokeLinecap="round" />
        <path d="M19 19 L22 13 M27 19 L30 13" strokeLinecap="round" />
        <path d="M19 13 L22 19 M27 13 L30 19" strokeLinecap="round" />
        <path d="M15 24 h0.01" strokeLinecap="round" strokeWidth="3" />
      </svg>
      <div>
        <div className="wordmark">Dead Parrots</div>
        <div className="sub">RIP TIDE League</div>
      </div>
    </div>
  );
}
