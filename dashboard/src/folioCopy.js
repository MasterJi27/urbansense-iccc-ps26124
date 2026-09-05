/** Verbatim first-viewport copy from the approved Ward Register comp. */

export const COMP_FOLIO = {
  wordmark: "URBANSENSE",
  register: "ICCC COMMAND REGISTER",
  folio: "FOLIO 07 - ENTRY 0153",
  serial: "ENTRY 0153",
  eventCode: "EVENT-08B183",
  type: "TRAFFIC_CONGESTION",
  typeHi: "प्रकार",
  corridor: "Barapullah",
  bus: "BUS-305",
  gps: "28.61658, 77.21508",
  acc: "4.5 m",
  time: "2026-09-04 09:32:19 IST",
  lat: 28.61658,
  lng: 77.21508,
  howHead: "HOW DETERMINED",
  howHeadHi: "कैसे तय",
  spatial: "spatial proximity 0.0 m",
  temporal: "temporal window 6 h",
  sources: "source diversity 2 sources",
  status: "RULE_BASED",
  score: "evidence score 0.87 - not certainty",
  plate: "DL8C••••",
  plateNote: "PLATE MASKED - DPDP - REVEAL REQUIRES INSPECTOR",
  assist: "ASSISTS AUTHORITIES - DOES NOT ACCUSE",
  mapCaption: "कॉरिडोर मानचित्र / CORRIDOR MAP - FOLIO 07",
  passes: "SAME DEFECT / N PASSES",
  passCaps: [
    { bus: "BUS-042", time: "09:12" },
    { bus: "BUS-305", time: "11:40" },
    { bus: "BUS-211", time: "14:05" },
    { bus: "BUS-117", time: "17:22" },
  ],
  endorse: "ICCC OFFICER ENDORSEMENT",
  endorseHi: "आई.सी.सी.सी. अनुमोदन",
  officer: "OFFICER ID",
  verify: "VERIFY",
  verifyHi: "सत्यापित करें",
  send: "SEND TO WARD",
  sendHi: "वार्ड को भेजें",
  wardQueue: "WARD 23-11 QUEUE  07 → 08",
  corridorCount: "CORRIDOR BARAPULLAH  04 → 05",
  note: "IMU+GPS TRIGGER 1.04 KB -",
  footerLeft: "IMU+GPS TRIGGER 1.04 KB - NO VIDEO UPLOADED",
  footerRight: "DEMONSTRATION DATA - NOT A LIVE DEPLOYMENT",
  openSl: "0153",
};

export const COMP_ROWS = [
  { sl: "0141", time: "09:12:04", code: "EVENT-08B153", type: "POTHOLE" },
  { sl: "0142", time: "09:14:22", code: "EVENT-08B161", type: "WATERLOGGING" },
  { sl: "0143", time: "09:16:41", code: "EVENT-08B167", type: "PEDESTRIAN_RISK" },
  { sl: "0144", time: "09:18:03", code: "EVENT-08B171", type: "ROAD_DAMAGE" },
  { sl: "0145", time: "09:21:17", code: "EVENT-08B174", type: "MISSING_ZEBRA" },
  { sl: "0146", time: "09:24:08", code: "EVENT-08B178", type: "TRAFFIC_CONGESTION" },
  { sl: "0147", time: "09:26:55", code: "EVENT-08B180", type: "RASH_DRIVING" },
  { sl: "0148", time: "09:28:12", code: "EVENT-08B181", type: "HIT_AND_RUN" },
  { sl: "0149", time: "09:29:40", code: "EVENT-08B182", type: "POTHOLE" },
  { sl: "0150", time: "09:30:11", code: "EVENT-08B184", type: "WATERLOGGING" },
  { sl: "0151", time: "09:31:02", code: "EVENT-08B185", type: "ROAD_DAMAGE" },
  { sl: "0152", time: "09:31:44", code: "EVENT-08B186", type: "MISSING_ZEBRA" },
  { sl: "0153", time: "09:32:19", code: "EVENT-08B183", type: "TRAFFIC_CONGESTION" },
  { sl: "0154", time: "09:33:07", code: "EVENT-08B187", type: "PEDESTRIAN_RISK" },
  { sl: "0155", time: "09:34:22", code: "EVENT-08B188", type: "POTHOLE" },
  { sl: "0156", time: "09:36:18", code: "EVENT-08B190", type: "RASH_DRIVING" },
  { sl: "0157", time: "09:38:01", code: "EVENT-08B192", type: "ROAD_DAMAGE" },
  { sl: "0158", time: "09:39:59", code: "EVENT-08B194", type: "HIT_AND_RUN" },
];

export const NAV_TABS = [
  { to: "/", hi: "अवलोकन", en: "OVERVIEW" },
  { to: "/events", hi: "घटनाएँ", en: "EVENTS" },
  { to: "/work-orders", hi: "वर्क ऑर्डर", en: "WORK ORDER" },
  { to: "/road-health", hi: "वार्ड", en: "WARD" },
];

export const CAPTURE_TABS = [
  { to: "/field", hi: "फ़ील्ड", en: "FIELD" },
  { to: "/cctv", hi: "सीसीटीवी", en: "CCTV" },
];

export const ATLAS_TABS = [
  { to: "/map", hi: "मानचित्र", en: "MAP" },
  { to: "/fleet", hi: "बेड़ा", en: "FLEET" },
  { to: "/bridge", hi: "पुल", en: "BRIDGE" },
];

export const MORE_TABS = [
  { to: "/assets", hi: "संपत्ति", en: "ASSETS" },
  { to: "/analytics", hi: "विश्लेषण", en: "ANALYTICS" },
  { to: "/sensors", hi: "सेंसर", en: "SENSORS" },
  { to: "/settings", hi: "सेटिंग", en: "SETTINGS" },
  { to: "/users", hi: "उपयोगकर्ता", en: "USERS" },
];

export const PASS_PLATES = [
  "/plates/pass-plate-1.png",
  "/plates/pass-plate-2.png",
  "/plates/pass-plate-3.png",
  "/plates/pass-plate-4.png",
];
