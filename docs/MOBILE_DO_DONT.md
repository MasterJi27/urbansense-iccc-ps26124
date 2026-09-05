# Mobile do / don’t — UrbanSense phone edge

For the team and BEL jury. Phone = 2GB Android, sunlight, one hand. Hindi + English.

---

## क्या करना है / DO

| EN | हिंदी |
|---|---|
| Mount one phone on the windshield. Press **START**. | एक फ़ोन विंडशील्ड पर लगाएँ। **START** दबाएँ। |
| Use IMU + GPS only. A bump (accel spike, no gyro turn) + speed 8–70 km/h → pothole candidate. | सिर्फ IMU + GPS। झटका (accel, घुमाव नहीं) + गति 8–70 → गड्ढा उम्मीदवार। |
| Send **~1KB JSON** on trigger. Heartbeat every 12s. | ट्रिगर पर **~1KB JSON** भेजें। हर 12 सेकंड heartbeat। |
| Offline queue (`pending_observations.json`, cap 500) must survive reboot. Press **SYNC** when net returns. | ऑफलाइन कतार रीबूट के बाद भी रहे। नेट आने पर **SYNC**। |
| Hindi labels for the driver. Big tap targets (START / STOP ≥ 54px). | ड्राइवर के लिए हिंदी लेबल। बड़े बटन (START / STOP)। |
| Say honestly: this phone is **LOW / CAPTURE_AND_SENSOR**. No on-device YOLO. | ईमानदारी: यह फ़ोन **LOW** है। फ़ोन पर YOLO नहीं। |
| Bridge: GPS 70–90m geofence + vibration batch. Screening only — flag for inspection. | पुल: 70–90m जियोफेंस + कंपन बैच। सिर्फ स्क्रीनिंग — जांच के लिए फ़्लैग। |
| School zone: GPS near school + speed drop → `PEDESTRIAN_RISK` (RULE_BASED). | स्कूल ज़ोन: स्कूल के पास GPS + गति गिरना → नियम-आधारित। |
| Battery saver: <20% batch 40, 20–50% batch 80, else 200. | बैटरी सेवर: <20% बैच 40, 20–50% 80, वरना 200। |
| One still photo **on demand** after a trigger — never a stream. | ट्रिगर के बाद एक स्टिल फ़ोटो — कभी स्ट्रीम नहीं। |
| Label every payload `ai_status`: RULE_BASED on phone, REAL only after backend still. | हर पेलोड पर `ai_status`: फ़ोन RULE_BASED, स्टिल के बाद ही REAL। |

Field run (60 seconds):

1. Edge tab → **START**
2. Drive. IMU/GPS fire by themselves.
3. If no net, queue fills. **SYNC** later.
4. Command center Live Map shows fused dots. Work order is ICCC → ward, not the phone.

---

## क्या नहीं करना है / DON’T

| EN | हिंदी |
|---|---|
| **Do not** run live multi-cam YOLO on the phone. | फ़ोन पर लाइव मल्टी-कैम YOLO **न चलाएँ**। |
| **Do not** upload continuous video. | लगातार वीडियो **अपलोड न करें**। |
| **Do not** claim federated learning. | फेडरेटेड लर्निंग **न कहें**। |
| **Do not** put a CameraPreview / live HUD as the default screen. | डिफ़ॉल्ट स्क्रीन पर लाइव कैमरा **न रखें**। |
| **Do not** OCR plates on the phone. ANPR is backend. | फ़ोन पर प्लेट OCR **न करें**। |
| **Do not** predict bridge collapse or a countdown. | पुल गिरने की भविष्यवाणी **न करें**। |
| **Do not** claim a waterlogging neural net or an Indian traffic-sign model. | जलभराव न्यूरल नेट या भारतीय साइन मॉडल **न कहें**। |
| **Do not** require a second / third / cabin camera for the jury demo. One phone is enough. | जूरी डेमो के लिए दूसरी कैमरा **ज़रूरी नहीं**। |
| **Do not** scan a QR on every bridge. GPS geofence is the bind. | हर पुल पर QR **न स्कैन करें**। |
| **Do not** hide SIMULATED / SEED labels. Seed payload ≠ REAL engine. | SIMULATED / SEED छुपाएँ **नहीं**। सीड ≠ इंजन। |

If a jury asks “where is the AI on the phone?” answer:

> Phone is the trigger. Intelligence is on the backend still + fusion. That is the product, not a missing feature.

---

See also: `docs/PHONE_ONLY_EDGE.md`, `PRODUCT.md`.
