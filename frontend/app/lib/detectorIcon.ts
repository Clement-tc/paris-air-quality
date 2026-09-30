// A "radar / target" marker: a centre dot inside concentric rings.
// White fill so deck.gl's IconLayer getColor can tint it to the AQI band colour.
// Encoded as a data URL because IconLayer loads icons as images.
const SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="22" fill="none" stroke="white" stroke-width="2.5" opacity="0.35"/>
  <circle cx="32" cy="32" r="14" fill="none" stroke="white" stroke-width="3" opacity="0.65"/>
  <circle cx="32" cy="32" r="6" fill="white"/>
</svg>`.trim();

export const DETECTOR_ICON_URL =
  "data:image/svg+xml;charset=utf-8," + encodeURIComponent(SVG);

// Anchor at the centre so the rings sit on the coordinate.
export const DETECTOR_ICON = {
  url: DETECTOR_ICON_URL,
  width: 64,
  height: 64,
  anchorX: 32,
  anchorY: 32,
};
