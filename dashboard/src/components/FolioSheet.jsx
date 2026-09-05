import { CircleMarker } from "react-leaflet";
import CorridorMap from "./CorridorMap.jsx";
import { NavLink } from "react-router-dom";
import { COMP_FOLIO, COMP_ROWS, NAV_TABS, PASS_PLATES } from "../folioCopy.js";

function tabActive(to, pathname) {
  if (to === "/") return pathname === "/" || pathname === "/folio";
  if (to === "/events") return pathname.startsWith("/events") || pathname === "/folio";
  return pathname.startsWith(to);
}

export default function FolioSheet({
  data = COMP_FOLIO,
  rows = COMP_ROWS,
  pathname = "/folio",
  onVerify,
  onSendWard,
  endorsed = false,
  wardFrom = 7,
  wardTo = 8,
  corridorFrom = 4,
  corridorTo = 5,
}) {
  const openSl = data.openSl || "0153";
  const center = [data.lat ?? 28.61658, data.lng ?? 77.21508];
  const wardLine = data.wardQueue || `WARD 23-11 QUEUE  ${String(wardFrom).padStart(2, "0")} → ${String(wardTo).padStart(2, "0")}`;
  const corridorLine = data.corridorCount || `CORRIDOR BARAPULLAH  ${String(corridorFrom).padStart(2, "0")} → ${String(corridorTo).padStart(2, "0")}`;

  return (
    <main className="folio" aria-label="ICCC command register folio">
      <div className="r-masthead-wordmark folio-wordmark">
        <div className="folio-brand">{data.wordmark}</div>
        <div className="folio-brand-sub">{data.register}</div>
      </div>

      <nav className="r-masthead-nav folio-nav" aria-label="Primary">
        {NAV_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={() => `folio-tab${tabActive(tab.to, pathname) ? " is-active" : ""}`}
          >
            <span className="folio-tab-hi">{tab.hi}</span>
            <span className="folio-tab-en">{tab.en}</span>
          </NavLink>
        ))}
      </nav>

      <p className="r-masthead-folio folio-locator">{data.folio}</p>

      <div className="r-register-head folio-reg-head">
        <span>SL.</span>
        <span>TIME<br />समय</span>
        <span>EVENT CODE</span>
        <span>TYPE<br />प्रकार</span>
      </div>

      <ol className="r-register-rows folio-reg-rows">
        {rows.map((row) => (
          <li key={row.sl} className={row.sl === openSl ? "is-open" : undefined}>
            <span className="folio-sl">{row.sl}</span>
            <span className="folio-time">{row.time}</span>
            <span className="folio-code">{row.code}</span>
            <span className="folio-type">{row.type}</span>
          </li>
        ))}
      </ol>

      <p className="r-register-note folio-reg-note">
        {data.note}
        <br />
        CONFIDENCE {data.status}
      </p>

      <div className="r-entry-serial folio-serial-block">
        <div className="folio-entry">{data.serial}</div>
        <div className="folio-event-code">{data.eventCode}</div>
      </div>

      <dl className="r-entry-fields folio-fields">
        <div>
          <dt>TYPE / {data.typeHi}</dt>
          <dd>{data.type}</dd>
        </div>
        <div>
          <dt>CORRIDOR</dt>
          <dd>{data.corridor}</dd>
        </div>
        <div>
          <dt>BUS</dt>
          <dd>{data.bus}</dd>
        </div>
        <div>
          <dt>GPS</dt>
          <dd>{data.gps}  ACC {data.acc}</dd>
        </div>
        <div>
          <dt>TIME</dt>
          <dd>{data.time}</dd>
        </div>
      </dl>

      <section className="r-how-determined folio-how">
        <h3>{data.howHead} / {data.howHeadHi}</h3>
        <p>{data.spatial}</p>
        <p>{data.temporal}</p>
        <p>{data.sources}</p>
        <p>STATUS: {data.status}</p>
        <p>{data.score}</p>
      </section>

      <div className="r-plate-field folio-plate">
        <div className="folio-plate-score">{data.score}</div>
        <div>PLATE {data.plate}</div>
        <div className="folio-plate-note">{data.plateNote}</div>
      </div>

      <p className="r-assist-line folio-assist">
        <span className="folio-plate-note">{data.plateNote}</span>
        <span>{data.assist}</span>
      </p>

      <section className="r-map-frame folio-map" aria-label={data.mapCaption}>
        <div className="folio-map-caption">{data.mapCaption}</div>
        <CorridorMap center={center} zoom={14} className="folio-leaflet" scrollWheelZoom={false} zoomControl={false} hideCaption>
          <CircleMarker center={center} radius={10} pathOptions={{ color: "#b0342b", fillColor: "#b0342b", fillOpacity: 0.85 }} />
        </CorridorMap>
      </section>

      <p className="r-passes-caption folio-passes-caption">{data.passes}</p>

      <figure className="r-pass-plate-1 folio-pass">
        <img src={PASS_PLATES[0]} alt="" />
      </figure>
      <figure className="r-pass-plate-2 folio-pass">
        <img src={PASS_PLATES[1]} alt="" />
      </figure>
      <figure className="r-pass-plate-3 folio-pass">
        <img src={PASS_PLATES[2]} alt="" />
      </figure>
      <figure className="r-pass-plate-4 folio-pass">
        <img src={PASS_PLATES[3]} alt="" />
      </figure>

      <div className="r-pass-captions folio-pass-caps">
        {data.passCaps.map((cap) => (
          <span key={cap.bus}>
            {cap.bus}
            <br />
            {cap.time}
          </span>
        ))}
      </div>

      <div className="r-endorsement-block folio-endorse">
        <div>{data.endorse} — {data.endorseHi}</div>
        <div className="folio-sign-line" />
        <div className="folio-officer">{data.officer} ________</div>
      </div>

      <button
        type="button"
        className={`r-stamp-verify folio-stamp${endorsed ? " is-stamped" : ""}`}
        onClick={onVerify}
      >
        <span>{data.verify}</span>
        <span>{data.verifyHi}</span>
      </button>

      <button
        type="button"
        className="r-stamp-send-ward folio-stamp"
        onClick={onSendWard}
      >
        <span>{data.send}</span>
        <span>{data.sendHi}</span>
      </button>

      <p className="r-propagation-counters folio-propagate">
        {wardLine}
        <br />
        {corridorLine}
      </p>

      <footer className="r-footer-strip folio-foot">
        <span>{data.footerLeft}</span>
        <span>{data.footerRight}</span>
      </footer>
    </main>
  );
}
