// SatHub brand mark: orbit ring + satellite sweep, same artwork as the
// favicon (public/favicon.svg) so the browser tab, login page and header
// all show one consistent icon.
export function SatHubMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden>
      <circle cx="32" cy="32" r="7" fill="currentColor" />
      <path d="M32 32 L47 17" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path
        d="M17.5 46.5 A21 21 0 0 1 17.5 17.5"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        opacity="0.85"
      />
      <path
        d="M24 50 A26 26 0 0 1 14 36"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        opacity="0.45"
      />
      <circle cx="47" cy="17" r="3.4" fill="currentColor" opacity="0.9" />
    </svg>
  );
}
