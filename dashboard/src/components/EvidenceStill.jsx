import { useEffect, useRef, useState } from "react";
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

function isVideoUrl(url) {
  const lower = String(url || "").toLowerCase();
  return lower.includes(".webm") || lower.includes(".mp4");
}

export default function EvidenceStill({ url, liveUrl = "", alt = "Field still" }) {
  const [src, setSrc] = useState("");
  const [liveSrc, setLiveSrc] = useState("");
  const [err, setErr] = useState("");
  const [held, setHeld] = useState(false);
  const videoRef = useRef(null);

  useEffect(() => {
    let stillObj = "";
    let liveObj = "";
    let cancelled = false;

    async function load(path, set) {
      if (!path) {
        set("");
        return "";
      }
      const token = getToken();
      const href = `${API}${path.startsWith("/") ? path : `/${path}`}`;
      const res = await fetch(href, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error("Still not available");
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      if (!cancelled) set(objectUrl);
      return objectUrl;
    }

    Promise.all([
      load(evidencePath(url), setSrc).then((u) => { stillObj = u; }),
      liveUrl ? load(evidencePath(liveUrl), setLiveSrc).then((u) => { liveObj = u; }) : Promise.resolve(""),
    ]).then(() => {
      if (!cancelled) setErr("");
    }).catch((exc) => {
      if (!cancelled) {
        setSrc("");
        setLiveSrc("");
        setErr(exc.message || "Still not available");
      }
    });

    return () => {
      cancelled = true;
      if (stillObj) URL.revokeObjectURL(stillObj);
      if (liveObj) URL.revokeObjectURL(liveObj);
    };
  }, [url, liveUrl]);

  useEffect(() => {
    const vid = videoRef.current;
    if (!vid) return undefined;
    if (held) {
      vid.currentTime = 0;
      vid.play().catch(() => {});
    } else {
      vid.pause();
    }
    return undefined;
  }, [held]);

  if (!url) return null;
  if (err) return <p className="muted" style={{ padding: 14 }}>{err}</p>;
  if (!src) return <p className="muted" style={{ padding: 14 }}>Loading still…</p>;

  const canLive = Boolean(liveSrc) && isVideoUrl(liveUrl);

  return (
    <figure className="evidence-still" style={{ margin: 0 }}>
      <div
        className={`live-photo ${held && canLive ? "is-live" : ""}`}
        onPointerDown={() => setHeld(true)}
        onPointerUp={() => setHeld(false)}
        onPointerLeave={() => setHeld(false)}
        onPointerCancel={() => setHeld(false)}
      >
        {canLive ? (
          <video
            ref={videoRef}
            src={liveSrc}
            poster={src}
            muted
            playsInline
            loop
            style={{ width: "100%", display: held ? "block" : "none", maxHeight: 360, objectFit: "contain", background: "#1a1814" }}
          />
        ) : null}
        <img
          src={src}
          alt={alt}
          style={{ width: "100%", display: held && canLive ? "none" : "block", maxHeight: 360, objectFit: "contain", background: "#1a1814" }}
        />
      </div>
      <figcaption className="muted" style={{ fontSize: 12, padding: "8px 12px" }}>
        {canLive ? "Hold to play the ~2s live clip around this still. Not a 24×7 stream." : "Field still · auth-gated evidence. Not a live stream."}
      </figcaption>
    </figure>
  );
}
