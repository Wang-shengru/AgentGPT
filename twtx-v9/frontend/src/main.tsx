import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

/** Deterministic dark-green pixel camouflage, generated once as an SVG data URI. */
function camoTexture(): string {
  const cols = ["#1f2a16", "#2a3a1d", "#33452250", "#3d4f27", "#18210f", "#465a2c"];
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const cell = 4, w = 96, h = 24;
  let rects = "";
  for (let y = 0; y < h; y += cell)
    for (let x = 0; x < w; x += cell) {
      const c = cols[Math.floor(rnd() * cols.length)];
      // blobby clusters: extend horizontally sometimes
      const span = rnd() < 0.35 ? cell * 2 : cell;
      rects += `<rect x="${x}" y="${y}" width="${span}" height="${cell}" fill="${c}"/>`;
    }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" shape-rendering="crispEdges">${rects}</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
document.documentElement.style.setProperty("--camo-img", camoTexture());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
