import { useEffect, useState } from "react";
import { API, getToken } from "../api";

export function evidencePath(url) {
  if (!url) return "";
  if (url.startsWith("/")) return url;
  try {
    const parsed = new URL(url, window.location.origin);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return url.startsWith("http") ? "" : `/${url}`;
  }
}

export default function EvidenceStill({ url, alt = "Field still" }) {
  const [src, setSrc] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    const path = evidencePath(url);
    if (!path) {
      setErr("");
      setSrc("");
      return undefined;
    }
    const token = getToken();
    const href = `${API}${path.startsWith("/") ? path : `/${path}`}`;
    fetch(href, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((res) => {
        if (!res.ok) throw new Error("Still not available");
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
        setErr("");
      })
      .catch((exc) => {
        if (!cancelled) {
          setSrc("");
          setErr(exc.message || "Still not available");
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (!url) return null;
  if (err) return <p className="muted" style={{ padding: 14 }}>{err}</p>;
  if (!src) return <p className="muted" style={{ padding: 14 }}>Loading still…</p>;
  return (
    <figure className="evidence-still" style={{ margin: 0 }}>
      <img
        src={src}
        alt={alt}
        style={{ width: "100%", display: "block", maxHeight: 360, objectFit: "contain", background: "#1a1814" }}
      />
      <figcaption className="muted" style={{ fontSize: 12, padding: "8px 12px" }}>
        Field still · auth-gated evidence. Not a live stream.
      </figcaption>
    </figure>
  );
}
