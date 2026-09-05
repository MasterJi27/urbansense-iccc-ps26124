import { useEffect, useState } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import { API, api } from "../api";

const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

export function useCorridorTiles() {
  const [cfg, setCfg] = useState(null);
  useEffect(() => {
    api("/maps/config")
      .then(setCfg)
      .catch(() => setCfg({ enabled: false, provider: "OpenStreetMap", honesty: "RULE_BASED" }));
  }, []);
  const enabled = Boolean(cfg?.enabled && cfg?.tile_url);
  const tileUrl = enabled ? `${API || ""}${cfg.tile_url}` : OSM_URL;
  return {
    ready: cfg != null,
    enabled,
    url: tileUrl,
    attribution: enabled ? "&copy; Azure Maps" : "&copy; OpenStreetMap",
    caption: enabled ? "Azure Maps" : "Leaflet + OSM (Azure Maps key not set)",
    provider: cfg?.provider || "OpenStreetMap",
    honesty: cfg?.honesty || "RULE_BASED",
  };
}

export function CorridorTiles() {
  const tiles = useCorridorTiles();
  if (!tiles.ready) return null;
  return <TileLayer key={tiles.url} url={tiles.url} attribution={tiles.attribution} />;
}

export default function CorridorMap({
  center,
  zoom = 12,
  height,
  style,
  className,
  scrollWheelZoom = true,
  zoomControl = true,
  hideCaption = false,
  children,
}) {
  const tiles = useCorridorTiles();
  const box = { height: height ?? style?.height ?? 260, width: "100%", ...style };
  if (!tiles.ready) {
    return <div className="muted" style={{ ...box, display: "grid", placeItems: "center" }}>Loading map…</div>;
  }
  return (
    <div className="corridor-map">
      {!hideCaption && (
        <div className="corridor-map-caption muted" style={{ fontSize: 11, padding: "6px 10px" }}>
          {tiles.caption}
        </div>
      )}
      <MapContainer
        center={center}
        zoom={zoom}
        className={className}
        style={box}
        scrollWheelZoom={scrollWheelZoom}
        zoomControl={zoomControl}
      >
        <TileLayer key={tiles.url} url={tiles.url} attribution={tiles.attribution} />
        {children}
      </MapContainer>
    </div>
  );
}
