export function stampLine({ at, lat, lng, bus, bay }) {
  const place = lat != null && lng != null ? `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}` : "";
  return [at || "", place, bus || "", bay || ""].filter(Boolean).join(" ");
}

export function nextJpegQuality(size, quality, target = 150 * 1024) {
  if (size <= target || quality <= 0.4) return quality;
  return Math.round((quality - 0.08) * 100) / 100;
}
