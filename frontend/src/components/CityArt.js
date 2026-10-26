// Original artwork for Bengaluru Pulse (drawn in SVG for this project; no third-party
// imagery): topographic contours, a sun, a stylised road network and a skyline with a
// dome silhouette in the spirit of the city's civic architecture. Purely decorative.
export default function CityArt({ className = "" }) {
  return (
    <svg className={`city-art ${className}`} viewBox="0 0 400 240" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="ca-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#30152F" />
          <stop offset="0.62" stopColor="#5925B5" />
          <stop offset="1" stopColor="#F47735" />
        </linearGradient>
        <radialGradient id="ca-sun" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFD3B5" />
          <stop offset="0.55" stopColor="#F47735" />
          <stop offset="1" stopColor="#F47735" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="400" height="240" fill="url(#ca-sky)" />
      <circle cx="292" cy="120" r="70" fill="url(#ca-sun)" opacity="0.9" />
      <g fill="none" stroke="#F5EEE5" strokeOpacity="0.22" strokeWidth="0.8">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <path key={i} d={`M-10 ${70 + i * 16} C 80 ${40 + i * 18}, 160 ${110 + i * 12}, 250 ${72 + i * 15} S 380 ${96 + i * 14}, 420 ${60 + i * 17}`} />
        ))}
      </g>
      <g fill="none" stroke="#CDBFF0" strokeOpacity="0.35" strokeWidth="0.6">
        <path d="M0 210 L400 150" />
        <path d="M60 240 L160 120 L400 96" />
        <path d="M0 160 L210 190 L400 230" />
      </g>
      <g fill="#171419">
        <path d="M0 240V196h18v-14h12v14h10v-26h16v26h8v-18h14v18h10v-34h6v-6h10v6h6v34h12v-22h16v22h8V170h4a22 22 0 0 1 44 0h4v-8h6v8h4v70Z" />
        <path d="M172 170a22 22 0 0 1 44 0Z" fill="#30152F" />
        <rect x="193" y="138" width="2" height="10" />
        <path d="M232 240v-30h14v-20h18v20h12v-38h20v38h10v-16h16v16h12v-26h18v26h12v-12h36v42Z" />
      </g>
      <g fill="#F47735">
        <circle cx="110" cy="208" r="1.6" />
        <circle cx="280" cy="214" r="1.6" />
        <circle cx="330" cy="200" r="1.6" />
      </g>
    </svg>
  );
}
