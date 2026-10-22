// Thin-outline icon set (1.5px strokes) drawn for Bengaluru Pulse. Decorative by default.
const PATHS = {
  compass: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm3.5 5.5-2 5-5 2 2-5 5-2Z",
  pulse: "M3 12h4l2-5 4 10 2-5h6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  shield: "M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3Z",
  login: "M10 17l5-5-5-5M15 12H3M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5",
  logout: "M14 7l5 5-5 5M19 12H8M10 20H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5",
  car: "M5 16h14M6.5 16v2M17.5 16v2M4 16v-4l2-5h12l2 5v4M4 12h16M7.5 14h1M15.5 14h1",
  moto: "M5 17a3 3 0 1 0 0-.01M19 17a3 3 0 1 0 0-.01M5 17l4-6h5l3 6M12 11l-1-3h3M14 11h3l2 3",
  bike: "M5.5 17a3.5 3.5 0 1 0 0-.01M18.5 17a3.5 3.5 0 1 0 0-.01M5.5 17 9 9h5l4.5 8M9 9 7.5 6H6M12 17l2-8",
  walk: "M13 4.5a1.5 1.5 0 1 0 0-.01M10 21l2-6 2.5 2.5V21M8 12l2-4 4 1.5 2 3.5M10 8l-1 5",
  swap: "M7 4v16M7 20l-3-3M7 20l3-3M17 20V4M17 4l-3 3M17 4l3 3",
  locate: "M12 2v3M12 19v3M2 12h3M19 12h3M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0 4a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z",
  pin: "M12 21s-6-5.6-6-11a6 6 0 1 1 12 0c0 5.4-6 11-6 11Zm0-8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l3 2",
  cloud: "M7 18h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 9.3 4.5 4.5 0 0 0 7 18Z",
  rain: "M7 14h10a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.2 5.3 4.5 4.5 0 0 0 7 14ZM8 17l-1 3M12 17l-1 3M16 17l-1 3",
  alert: "M12 4 2.5 20h19L12 4Zm0 6v4m0 3v.01",
  route: "M6 19a2 2 0 1 0 0-.01M18 5a2 2 0 1 0 0-.01M6 17V9a3 3 0 0 1 3-3h1M18 7v8a3 3 0 0 1-3 3h-1M10 6h4M10 18h4",
  arrow: "M5 12h14M13 6l6 6-6 6",
  layers: "M12 3 2 8l10 5 10-5-10-5ZM2 13l10 5 10-5M2 17.5 12 22l10-4.5",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  road: "M8 3 5 21M16 3l3 18M12 4v3M12 10v3M12 16v3",
  home: "M4 11 12 4l8 7M6 9.5V20h4.5v-5.5h3V20H18V9.5",
  book: "M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5v-15ZM5 19.5A1.5 1.5 0 0 0 6.5 21H19M9 7h6M9 10.5h6",
  chart: "M4 20h16M7 17v-5M12 17V7M17 17v-8",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 8v5m0-8.5v.01",
};

export default function Icon({ name, size = 20, className = "", title }) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}
