// SatHub brand mark — the platform logo (public/logo-square.png).
// Kept as a component so every usage stays consistent and swappable.
export function SatHubMark({ size = 20 }: { size?: number }) {
  return (
    <img
      src="/logo-square.png"
      alt="SatHub"
      width={size}
      height={size}
      style={{ objectFit: 'contain', display: 'block' }}
    />
  );
}
