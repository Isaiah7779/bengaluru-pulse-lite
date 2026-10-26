import { useState } from "react";
import heroCollage from "../assets/hero-collage.svg";

// Decorative hero collage (original SVG in src/assets; bundled and cached by the build).
// If the file fails to load, the figure keeps its CSS gradient so the layout never breaks.
export default function HeroArt({ className = "" }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className={`hero-art ${failed ? "is-fallback" : ""} ${className}`} aria-hidden="true">
      {!failed && <img src={heroCollage} alt="" decoding="async" draggable="false" onError={() => setFailed(true)} />}
    </figure>
  );
}
