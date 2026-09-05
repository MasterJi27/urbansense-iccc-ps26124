import { Navigate, NavLink, Route, Routes, useNavigate, useLocation } from "react-router-dom";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { getToken, getScope, clearSession, api } from "./api";
import Login from "./pages/Login.jsx";
import FieldCamera from "./pages/FieldCamera.jsx";
import CctvBridge from "./pages/CctvBridge.jsx";
import CitizenReport from "./pages/CitizenReport.jsx";
import Events from "./pages/Events.jsx";
import EventDetail from "./pages/EventDetail.jsx";
import Fleet from "./pages/Fleet.jsx";
import Assets from "./pages/Assets.jsx";
import AssetDetail from "./pages/AssetDetail.jsx";
import WorkOrders from "./pages/WorkOrders.jsx";
import Sensors from "./pages/Sensors.jsx";
import Users from "./pages/Users.jsx";
import Settings from "./pages/Settings.jsx";
import RoadHealth from "./pages/RoadHealth.jsx";
import { ToastProvider } from "./components/Toast.jsx";
import { UiProvider, useUi } from "./i18n.jsx";
import FolioSheet from "./components/FolioSheet.jsx";
import { ATLAS_TABS, CAPTURE_TABS, MORE_TABS, NAV_TABS } from "./folioCopy.js";

const Overview = lazy(() => import("./pages/Overview.jsx"));
const LiveMap = lazy(() => import("./pages/LiveMap.jsx"));
const Analytics = lazy(() => import("./pages/Analytics.jsx"));
const BridgeHealth = lazy(() => import("./pages/BridgeHealth.jsx"));

function Guard({ children }) {
  const loc = useLocation();
  if (!getToken()) {
    const next = encodeURIComponent(`${loc.pathname}${loc.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (getScope() === "field") {
    return <Navigate to="/field" replace />;
  }
  return children;
}

function useRole() {
  return (localStorage.getItem("urbansense_role") || "ADMIN").toUpperCase();
}

function Shell() {
  const nav = useNavigate();
  const loc = useLocation();
  const role = useRole();
  const { t, lang, toggleLang } = useUi();
  const [q, setQ] = useState("");
  const [liveCount, setLiveCount] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifs, setNotifs] = useState([]);
  const [theme, setTheme] = useState(() => localStorage.getItem("urbansense_theme") || "light");
  const cmdRef = useRef(null);
  const notifRef = useRef(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteIdx, setPaletteIdx] = useState(0);
  const [palEvents, setPalEvents] = useState([]);
  const [palBuses, setPalBuses] = useState([]);
  const [palAssets, setPalAssets] = useState([]);
  const [palLoading, setPalLoading] = useState(false);
  const paletteCache = useRef(null);
  const paletteRef = useRef(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
    try { localStorage.setItem("urbansense_theme", theme); } catch {}
  }, [theme]);

  const title = useMemo(() => {
    const p = loc.pathname;
    if (p === "/") return t("overview");
    if (p.startsWith("/map")) return t("liveMap");
    if (p.startsWith("/events")) return t("events");
    if (p.startsWith("/fleet")) return t("fleet");
    if (p.startsWith("/assets")) return t("assets");
    if (p.startsWith("/road-health")) return t("roadHealth");
    if (p.startsWith("/bridge")) return t("bridge");
    if (p.startsWith("/work-orders")) return t("workOrders");
    if (p.startsWith("/analytics")) return t("analytics");
    if (p.startsWith("/sensors")) return t("sensors");
    if (p.startsWith("/users")) return t("users");
    if (p.startsWith("/settings")) return t("settings");
    if (p.startsWith("/field")) return t("fieldUnit");
    if (p.startsWith("/cctv")) return t("cctvUnit");
    return "UrbanSense";
  }, [loc.pathname, t]);

  useEffect(() => {
    api("/analytics/summary").then((s) => setLiveCount(s.total_events)).catch(()=>{});
    const onKey = (e) => {
      if (e.key === "Escape") {
        setDrawerOpen(false);
        setNotifOpen(false);
        setPaletteOpen(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        cmdRef.current?.focus();
        setPaletteOpen(true);
        ensurePaletteData();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loc.pathname]);

  // Bell — count of recent CRITICAL notifications (bridge CRITICAL auto-WO + citizen)
  useEffect(() => {
    let alive = true;
    let timer;
    const fetchNotifs = () => {
      if (!getToken()) return;
      // try notifications endpoint (NotificationLog), fallback to events filter
      api("/notifications?limit=50").then((data) => {
        if (!alive) return;
        const list = Array.isArray(data) ? data : [];
        setNotifs(list);
        const crit = list.filter((n) => (n.severity || "").toUpperCase() === "CRITICAL").length;
        if (crit > 0) setNotifCount(crit);
        else {
          // fallback to analytics critical count if no notification logs yet
          api("/analytics/summary").then((s)=> { if (alive) setNotifCount(s.critical_events || 0); }).catch(()=>{});
        }
      }).catch(() => {
        // fallback: count CRITICAL events directly
        api("/events?limit=200").then((evs) => {
          if (!alive || !Array.isArray(evs)) return;
          const c = evs.filter((e) => e.severity === "CRITICAL").length;
          setNotifCount(c);
          setNotifs(evs.filter((e)=>e.severity==="CRITICAL").slice(0,8).map((e)=>({id:e.id, title:`${e.public_code} — ${e.event_type}`, message:e.fusion_reason||e.event_type, severity:e.severity, created_at:e.created_at})));
        }).catch(()=>{});
      });
    };
    fetchNotifs();
    timer = setInterval(fetchNotifs, 30000);
    // click outside to close
    const onClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false);
      if (paletteRef.current && !paletteRef.current.contains(e.target)) setPaletteOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => { alive = false; clearInterval(timer); document.removeEventListener("mousedown", onClick); };
  }, [loc.pathname]);

  useEffect(() => { setDrawerOpen(false); }, [loc.pathname]);

  useEffect(() => {
    const onEsc = (e) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, []);

  function onSearch(e) {
    e.preventDefault();
    setPaletteOpen(false);
    const v = q.trim();
    if (!v) return;
    if (v.startsWith("EVENT") || v.startsWith("event")) nav(`/events/${v}`);
    else if (v.startsWith("BUS")) nav(`/fleet`);
    else nav(`/events`);
  }

  // Command palette — lazy fetch once (cached in ref), fuzzy = case-insensitive substring on code+type+status
  function ensurePaletteData() {
    if (paletteCache.current) {
      const c = paletteCache.current;
      if (!c.fetching) { setPalEvents(c.evs); setPalBuses(c.buses); setPalAssets(c.assets); }
      return;
    }
    paletteCache.current = { fetching: true, evs: [], buses: [], assets: [] };
    setPalLoading(true);
    Promise.all([
      api("/events?limit=200").catch(() => []),
      api("/buses").catch(() => []),
      api("/assets").catch(() => []),
    ]).then(([evs, buses, assets]) => {
      const norm = (v) => (Array.isArray(v) ? v : v?.events || v?.buses || v?.assets || v?.items || []);
      const c = { fetching: false, evs: norm(evs), buses: norm(buses), assets: norm(assets) };
      paletteCache.current = c;
      setPalEvents(c.evs); setPalBuses(c.buses); setPalAssets(c.assets);
    }).catch(() => { paletteCache.current = null; })
      .finally(() => setPalLoading(false));
  }

  const palQ = q.trim().toLowerCase();
  const palMatchEv = useMemo(() => {
    const list = palQ
      ? palEvents.filter((e) => `${e.public_code || ""} ${e.event_type || ""} ${e.status || ""} ${e.severity || ""}`.toLowerCase().includes(palQ))
      : palEvents;
    return list.slice(0, 5);
  }, [palEvents, palQ]);
  const palMatchBus = useMemo(() => {
    const list = palQ
      ? palBuses.filter((b) => `${b.code || ""} ${b.registration || ""} ${b.route_code || ""} ${b.status || ""}`.toLowerCase().includes(palQ))
      : palBuses;
    return list.slice(0, 5);
  }, [palBuses, palQ]);
  const palMatchAsset = useMemo(() => {
    const list = palQ
      ? palAssets.filter((a) => `${a.code || ""} ${a.name || ""} ${a.asset_type || ""} ${a.condition || ""} ${a.status || ""}`.toLowerCase().includes(palQ))
      : palAssets;
    return list.slice(0, 5);
  }, [palAssets, palQ]);
  const palFlat = useMemo(() => ([
    ...palMatchEv.map((e) => ({ kind: "event", key: `ev-${e.id ?? e.public_code}`, id: e.id ?? e.public_code, title: e.public_code || String(e.id ?? "event"), sub: `${e.event_type || ""} • ${e.status || e.severity || ""}`.replace(/^[ •]+|[ •]+$/g, "") })),
    ...palMatchBus.map((b) => ({ kind: "bus", key: `bus-${b.id ?? b.code}`, id: b.id ?? b.code, title: b.code || b.registration || "bus", sub: `${b.registration || ""} • ${b.route_code || b.status || ""}`.replace(/^[ •]+|[ •]+$/g, "") })),
    ...palMatchAsset.map((a) => ({ kind: "asset", key: `as-${a.id ?? a.code}`, id: a.id ?? a.code, title: a.code || a.name || "asset", sub: `${a.asset_type || ""} • ${a.condition || a.status || ""}`.replace(/^[ •]+|[ •]+$/g, "") })),
  ]), [palMatchEv, palMatchBus, palMatchAsset]);
  const palActive = palFlat.length ? Math.min(Math.max(paletteIdx, 0), palFlat.length - 1) : 0;

  function goPal(item) {
    if (!item) return;
    setPaletteOpen(false);
    if (item.kind === "event") nav(`/events/${item.id}`);
    else if (item.kind === "asset") nav(`/assets/${item.id}`);
    else nav("/fleet");
  }

  function onPalKeyDown(e) {
    if (e.key === "ArrowDown" && paletteOpen && palFlat.length) {
      e.preventDefault();
      setPaletteIdx((i) => {
        const n = Math.min(i + 1, palFlat.length - 1);
        queueMicrotask(() => document.getElementById(`pal-opt-${n}`)?.scrollIntoView({ block: "nearest" }));
        return n;
      });
    } else if (e.key === "ArrowUp" && paletteOpen && palFlat.length) {
      e.preventDefault();
      setPaletteIdx((i) => {
        const n = Math.max(i - 1, 0);
        queueMicrotask(() => document.getElementById(`pal-opt-${n}`)?.scrollIntoView({ block: "nearest" }));
        return n;
      });
    } else if (e.key === "Enter" && paletteOpen && palFlat.length) {
      e.preventDefault();
      goPal(palFlat[palActive]);
    } else if (e.key === "Escape") {
      setPaletteOpen(false);
    }
  }

  const sections = [
    {
      label: t("ops"),
      links: [
        ["/", t("overview"), "▦"],
        ["/map", t("liveMap"), "◎"],
        ["/events", t("events"), "◉"],
        ["/fleet", t("fleet"), "🚌"],
      ],
    },
    {
      label: t("maint"),
      links: [
        ["/assets", t("assets"), "⬢"],
        ["/road-health", t("roadHealth"), "〰"],
        ["/bridge", t("bridge"), "⌇"],
        ["/work-orders", t("workOrders"), "⧉"],
      ],
    },
    {
      label: t("intel"),
      links: [[ "/analytics", t("analytics"), "◐"]],
    },
    {
      label: t("system"),
      links: [
        ["/sensors", t("sensors"), "⦿"],
        ...(role === "ADMIN" || role === "SUPER_ADMIN" ? [["/users", t("users"), "◒"]] : []),
        ["/settings", t("settings"), "⚙"],
      ],
    },
  ];

  const name = localStorage.getItem("urbansense_name") || "Operator";

  const moreTabs = MORE_TABS.filter((tab) => tab.to !== "/users" || role === "ADMIN" || role === "SUPER_ADMIN");
  const deskGroups = [
    { label: t("captureDesk"), tabs: CAPTURE_TABS },
    { label: t("atlasDesk"), tabs: ATLAS_TABS },
    { label: t("moreDesk"), tabs: moreTabs },
  ];

  return (
    <div className="register-shell">
      <header className="register-masthead">
        <div className="folio-wordmark">
          <div className="folio-brand">URBANSENSE</div>
          <div className="folio-brand-sub">ICCC COMMAND REGISTER</div>
        </div>
        <nav className="folio-nav" aria-label="Primary">
          {NAV_TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.to === "/"} className={({ isActive }) => `folio-tab${isActive ? " is-active" : ""}`}>
              <span className="folio-tab-hi">{tab.hi}</span>
              <span className="folio-tab-en">{tab.en}</span>
            </NavLink>
          ))}
        </nav>
        <p className="folio-locator">{name.toUpperCase()} · {role}</p>
      </header>
      <nav className="register-more" aria-label="Desks">
        {deskGroups.map((group) => (
          <span key={group.label} className="register-more-group">
            <span className="register-more-kicker">{group.label}</span>
            {group.tabs.map((tab) => (
              <NavLink key={tab.to} to={tab.to} className={({ isActive }) => `register-more-link${isActive ? " is-active" : ""}`}>
                <span>{tab.hi}</span>{tab.en}
              </NavLink>
            ))}
          </span>
        ))}
        <span className="register-more-user">
          {name.toUpperCase()} · {role} · {liveCount ?? "—"} OPEN ·{" "}
          <button type="button" className="register-more-link" style={{ border: 0, display: "inline", padding: 0 }} onClick={() => { clearSession(); nav("/login"); }}>
            SIGN OUT
          </button>
        </span>
      </nav>

      <div className="register-tools">
          <form ref={paletteRef} className="search" role="search" aria-label="Global search" onSubmit={onSearch} style={{position:"relative"}}>
            <span aria-hidden="true">⌕</span>
            <input ref={cmdRef} value={q} onChange={(e)=>{setQ(e.target.value); setPaletteOpen(true); setPaletteIdx(0); ensurePaletteData();}} onFocus={()=>{setPaletteOpen(true); setPaletteIdx(0); ensurePaletteData();}} onKeyDown={onPalKeyDown} placeholder={t("searchPh")} aria-label="Search events, buses, assets" aria-keyshortcuts="Control+k Meta+k" role="combobox" aria-expanded={paletteOpen} aria-controls="cmd-palette" aria-autocomplete="list" />
            <kbd aria-hidden="true">Ctrl K</kbd>
            {paletteOpen && (
              <div id="cmd-palette" className="notif-dropdown" role="listbox" aria-label="Command palette results" style={{left:0,right:0,width:"auto",top:"calc(100% + 8px)"}}>
                <div className="notif-list" style={{maxHeight:360}}>
                  {palLoading && palFlat.length === 0 ? (
                    <div className="notif-item"><div className="muted" style={{fontSize:12}}>Loading events, buses, assets…</div></div>
                  ) : palFlat.length === 0 ? (
                    <div className="notif-item"><div className="muted" style={{fontSize:12}}>No matches{q.trim() ? ` for “${q.trim()}”` : ""}.</div></div>
                  ) : (
                    [["Events","event"],["Buses","bus"],["Assets","asset"]].map(([label, kind]) => {
                      const items = palFlat.map((it, idx) => ({ ...it, idx })).filter((it) => it.kind === kind);
                      if (!items.length) return null;
                      return (
                        <div key={kind}>
                          <div className="section-title" style={{margin:0,padding:"10px 14px 4px"}}>{label}</div>
                          {items.map((it) => (
                            <div key={it.key} id={`pal-opt-${it.idx}`} role="option" aria-selected={it.idx === palActive} className="notif-item" style={it.idx === palActive ? {background:"var(--surface-2)",cursor:"pointer"} : {cursor:"pointer"}} onClick={()=>goPal(it)} onMouseEnter={()=>setPaletteIdx(it.idx)}>
                              <div style={{fontWeight:700,fontSize:13}}><span className="mono">{it.title}</span></div>
                              {it.sub ? <div className="muted" style={{fontSize:12}}>{it.sub}</div> : null}
                            </div>
                          ))}
                        </div>
                      );
                    })
                  )}
                </div>
                <div className="notif-foot"><span className="muted" style={{fontSize:11}}>↑↓ navigate • Enter opens{palFlat[palActive] ? ` — ${palFlat[palActive].title}` : ""} • Esc closes</span></div>
              </div>
            )}
          </form>

          <div className="top-actions">
            <button
              className="lang-toggle"
              type="button"
              title={lang === "hi" ? "Switch to English" : "हिंदी में देखें"}
              aria-label={lang === "hi" ? "Switch to English" : "Switch to Hindi"}
              aria-pressed={lang === "hi"}
              onClick={toggleLang}
            >
              {t("lang")}
            </button>
            <button className="icon-btn" title={t("liveMap")} aria-label={t("liveMap")} onClick={()=>nav("/map")}>◎</button>
            <button className="icon-btn" title={t("events")} aria-label={t("events")} onClick={()=>nav("/events")}>◉</button>
            <button
              className="theme-btn"
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              onClick={()=>setTheme((t)=> t === "dark" ? "light" : "dark")}
            >
              <span aria-hidden="true">{theme === "dark" ? "☀" : "◐"}</span>
            </button>
            <div className="notif-wrap" ref={notifRef}>
              <button className="icon-btn" title={`Notifications — ${notifCount} CRITICAL`} aria-label={`Notifications ${notifCount} critical`} aria-expanded={notifOpen} aria-haspopup="true" onClick={()=>setNotifOpen((v)=>!v)}>
                <span aria-hidden="true">🔔</span>
                {notifCount > 0 && (
                  <span className="notif-badge" aria-hidden="true">{notifCount > 99 ? "99+" : notifCount}</span>
                )}
              </button>
              {notifOpen && (
                <div className="notif-dropdown" role="dialog" aria-label="Critical notifications">
                  <div className="notif-head">
                    <b className="section-title" style={{margin:0}}>{t("critNotif")} {notifCount}</b>
                    <button className="btn ghost" style={{padding:"4px 8px",fontSize:12}} onClick={()=>setNotifOpen(false)}>Close</button>
                  </div>
                  <div className="notif-list">
                    {notifs.length === 0 ? (
                      <div className="empty" style={{padding:22}}><b>{t("allClear")}</b><div className="muted">No recent CRITICAL events.</div></div>
                    ) : (
                      notifs.slice(0,12).map((n)=>(
                        <div key={n.id} className="notif-item">
                          <div style={{fontWeight:700,fontSize:13,display:"flex",gap:8,alignItems:"center"}}>
                            <span className={`badge ${n.severity}`} style={{fontSize:10,padding:"2px 6px"}}>{n.severity}</span>
                            <span style={{flex:1,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{n.title}</span>
                          </div>
                          <div className="muted" style={{fontSize:12,lineHeight:1.4,display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden"}}>{n.message || n.detail || "—"}</div>
                          <div className="muted" style={{fontSize:11}}>{n.created_at ? new Date(n.created_at).toLocaleString() : ""}</div>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="notif-foot">
                    <button className="btn ghost" style={{flex:1,padding:"7px"}} onClick={()=>{ setNotifOpen(false); nav("/events"); }}>{t("viewEvents")}</button>
                    <button className="btn ghost" style={{flex:1,padding:"7px"}} onClick={()=>{ setNotifOpen(false); nav("/bridge"); }}>Bridge SHM</button>
                  </div>
                </div>
              )}
            </div>
            <button className="btn" onClick={()=>nav("/work-orders")}>NEW WORK ORDER</button>
          </div>
        </div>

        <div className="content">
          <Suspense fallback={<div>Loading...</div>}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/map" element={<LiveMap />} />
              <Route path="/fleet" element={<Fleet />} />
              <Route path="/events" element={<Events />} />
              <Route path="/events/:id" element={<EventDetail />} />
              <Route path="/assets" element={<Assets />} />
              <Route path="/assets/:id" element={<AssetDetail />} />
              <Route path="/road-health" element={<RoadHealth />} />
              <Route path="/bridge" element={<BridgeHealth />} />
              <Route path="/work-orders" element={<WorkOrders />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/sensors" element={<Sensors />} />
              <Route path="/users" element={<Users />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Suspense>
        </div>
    </div>
  );
}

export { useToast } from "./components/Toast.jsx";

export default function App() {
  return (
    <UiProvider>
      <ToastProvider>
        <Routes>
          <Route path="/folio" element={<FolioSheet pathname="/folio" />} />
          <Route path="/login" element={<Login />} />
          <Route path="/field" element={<FieldCamera />} />
          <Route path="/cctv" element={<CctvBridge />} />
          <Route path="/report" element={<CitizenReport />} />
          <Route path="/*" element={<Guard><Shell /></Guard>} />
        </Routes>
      </ToastProvider>
    </UiProvider>
  );
}
