// SatHub brand mark — abstract orbital symbol (not a literal satellite).
//
// Composition (per design brief): a closed elliptical orbit (rx 26, ry 12)
// tilted -25° around an abstract core; a diagonal trajectory crosses the
// composition, visible as two segments outside the ring, each ending in a
// node (top / bottom-right); a third node sits on the ring's left edge.
// Reads as orbit + trajectory + network. Flat vector, no glow, no shadow.
export function SatHubMarkColor({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden>
      <defs>
        <linearGradient id="sathub-ring" x1="10" y1="48" x2="54" y2="16" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563EB" />
          <stop offset="1" stopColor="#6366F1" />
        </linearGradient>
        <linearGradient id="sathub-core" x1="27" y1="37" x2="37" y2="27" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563EB" />
          <stop offset="1" stopColor="#4F46E5" />
        </linearGradient>
      </defs>
      {/* orbit ring */}
      <ellipse
        cx="32"
        cy="32"
        rx="26"
        ry="12"
        transform="rotate(-25 32 32)"
        stroke="url(#sathub-ring)"
        strokeWidth="3.6"
      />
      {/* trajectory segments outside the ring, each ending in a node */}
      <path d="M 35.4 9 L 37.8 14.5" stroke="#2563EB" strokeWidth="3" strokeLinecap="round" />
      <path d="M 47.5 39.9 L 53.4 48.5" stroke="#6366F1" strokeWidth="3" strokeLinecap="round" />
      {/* core */}
      <circle cx="32" cy="32" r="6.5" fill="url(#sathub-core)" />
      {/* nodes: top / bottom-right (trajectory ends) + one on the ring */}
      <circle cx="34" cy="6" r="3.4" fill="#2563EB" />
      <circle cx="55" cy="52" r="3.4" fill="#6366F1" />
      <circle cx="8.44" cy="43" r="3" fill="#8B5CF6" />
    </svg>
  );
}
