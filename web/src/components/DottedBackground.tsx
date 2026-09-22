/** Fixed full-viewport backdrop: a grid of dots fading from soft grey at the top toward
 * transparent — the Command Center direction contract's background texture. An inline SVG
 * pattern + radial-gradient mask stays a few KB of vector markup, never a raster asset. */
export function DottedBackground() {
  return (
    <svg
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
      aria-hidden="true"
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <pattern id="dg-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="1.4" cy="1.4" r="1.4" fill="#8b8b93" />
        </pattern>
        <radialGradient id="dg-fade" cx="50%" cy="0%" r="85%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
          <stop offset="55%" stopColor="#ffffff" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <mask id="dg-mask">
          <rect width="100%" height="100%" fill="url(#dg-fade)" />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="url(#dg-dots)" mask="url(#dg-mask)" />
    </svg>
  );
}
