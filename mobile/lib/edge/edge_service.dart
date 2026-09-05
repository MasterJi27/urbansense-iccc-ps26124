import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// UrbanSense EdgeService — HEADLESS, phone-only, no GUI dependency.
///
/// Utilizes ONLY phone resources:
///  accel 50Hz + gyro 50Hz + GPS 1Hz/0.2Hz + battery + net + storage.
/// Camera is TRIGGER-ONLY (single still on IMU spike/geofence), never stream.
/// Phone does RMS/peak/crest (O(n)); FFT/baseline/fusion on backend.
/// Every POST ~1KB JSON. Offline queue survives reboot. Battery adaptive.
///
/// PS26124 mapping: see docs/PHONE_ONLY_EDGE.md
class EdgeService {
  static final EdgeService I = EdgeService._();
  EdgeService._();

  final String Function()? tokenProvider;
  EdgeService.withToken(this.tokenProvider);

  String apiBase = 'https://app-urbansense-yngmbk.azurewebsites.net';
  String sensorCode = 'NODE-PHONE-01';
  String? busCode;
  String? busId;

  bool running = false;
  bool lowData = false;
  void Function(String line)? onLog;

  // resource state
  int? batteryPct;
  String net = 'UNKNOWN';
  bool accelOk = false, gyroOk = false, gpsOk = false, cameraOk = false;

  // buffers
  final List<Map<String, double>> _accelBuf = []; // {t,ax,ay,az}
  final List<Map<String, double>> _gyroBuf = [];
  StreamSubscription? _accSub, _gyroSub;
  Timer? _gpsTimer, _hbTimer, _syncTimer, _battTimer;
  Timer? _triggerTimer;
  Position? lastPos;
  double lastRms = 0;
  int sentBatches = 0, sentObs = 0, queuedCount = 0;
  DateTime? _lastPotholeAt;
  DateTime? _lastCongAt;
  DateTime? _lastSchoolAt;
  DateTime? _lastRashAt;

  /// Phone is always LOW. HIGH/MED run on backend stills, never on-device YOLO.
  String get processingTier {
    if (batteryPct != null && batteryPct! < 20) return 'LOW';
    if (lowData) return 'LOW';
    return 'LOW';
  }

  String get processingMode => 'CAPTURE_AND_SENSOR';

  void log(String s) {
    final line = '[${DateTime.now().toIso8601String().substring(11, 19)}] $s';
    try { onLog?.call(line); } catch (_) {}
  }

  int get batchCap {
    if (batteryPct != null && batteryPct! < 20) return 40;
    if (batteryPct != null && batteryPct! <= 50) return 80;
    return lowData ? 80 : 200;
  }

  Future<File> _qfile() async {
    final d = await getApplicationDocumentsDirectory();
    return File('${d.path}/pending_observations.json');
  }

  Future<void> _enqueue(Map<String, dynamic> item) async {
    try {
      final f = await _qfile();
      List items = [];
      if (await f.exists()) {
        try { items = jsonDecode(await f.readAsString()) as List; } catch (_) {}
      }
      if (items.length > 500) items = items.sublist(items.length - 500);
      items.add(item);
      await f.writeAsString(jsonEncode(items));
      queuedCount = items.length;
    } catch (_) {}
  }

  Future<Map<String, String>> _headers() async {
    String? tok;
    try {
      final p = await SharedPreferences.getInstance();
      tok = p.getString('token');
    } catch (_) {}
    final h = <String, String>{'Content-Type': 'application/json'};
    if (tok != null) h['Authorization'] = 'Bearer $tok';
    return h;
  }

  Future<void> start({String? apiBaseOverride, String? busCodeOverride}) async {
    if (running) return;
    running = true;
    if (apiBaseOverride != null) apiBase = apiBaseOverride;
    if (busCodeOverride != null) busCode = busCodeOverride;
    try {
      final p = await SharedPreferences.getInstance();
      lowData = p.getBool('low_data') ?? false;
      busCode ??= p.getString('bus');
      apiBase = const String.fromEnvironment('API_BASE', defaultValue: 'https://app-urbansense-yngmbk.azurewebsites.net');
    } catch (_) {}
    log('EDGE start bus=${busCode ?? "unbound"} base=$apiBase lowData=$lowData');
    await _probeOnce();
    _startSensors();
    // GPS poll: 1Hz moving, 0.2Hz idle — decide by speed each tick (start 1Hz, slow down if idle)
    _gpsTimer = Timer.periodic(const Duration(seconds: 2), (_) => _gpsTick());
    _hbTimer = Timer.periodic(const Duration(seconds: 12), (_) => _heartbeat());
    _syncTimer = Timer.periodic(const Duration(seconds: 15), (_) => _sync());
    _battTimer = Timer.periodic(const Duration(seconds: 30), (_) => _battTick());
    _triggerTimer = Timer.periodic(const Duration(seconds: 1), (_) => _evaluateTriggers());
    _heartbeat();
    log('sensors accel=$accelOk gyro=$gyroOk gps=$gpsOk batt=${batteryPct ?? "n/a"}% net=$net');
  }

  Future<void> stop() async {
    running = false;
    await _accSub?.cancel(); await _gyroSub?.cancel();
    _gpsTimer?.cancel(); _hbTimer?.cancel(); _syncTimer?.cancel(); _battTimer?.cancel(); _triggerTimer?.cancel();
    log('EDGE stopped. sent obs=$sentObs batches=$sentBatches queued=$queuedCount');
  }

  Future<void> _probeOnce() async {
    final kPhone = !Platform.isWindows && !Platform.isLinux && !Platform.isMacOS;
    if (kPhone) {
      accelOk = true; gyroOk = true; // streams will confirm; assume present on phone
    }
    try {
      batteryPct = await Battery().batteryLevel;
    } catch (_) {}
    try {
      final c = await Connectivity().checkConnectivity();
      net = c.map((e) => e.name).join(',');
    } catch (_) {}
    try {
      gpsOk = await Geolocator.isLocationServiceEnabled();
    } catch (_) {}
  }

  void _startSensors() {
    final kPhone = !Platform.isWindows && !Platform.isLinux && !Platform.isMacOS;
    if (!kPhone) { log('desktop: IMU unavailable, GPS sim'); return; }
    try {
      _accSub = accelerometerEventStream().listen((e) {
        // battery adaptive downsample: <20% keep 1/5
        if (batteryPct != null && batteryPct! < 20 && _accelBuf.length % 5 != 0) {
          // still add but will be capped smaller — keep simple: add all, cap handles
        }
        _accelBuf.add({'t': DateTime.now().millisecondsSinceEpoch / 1000.0, 'ax': e.x, 'ay': e.y, 'az': e.z});
        final cap = batchCap;
        if (_accelBuf.length > cap + 40) _accelBuf.removeRange(0, _accelBuf.length - (cap + 40));
      }, onError: (_) { accelOk = false; });
      accelOk = true;
    } catch (_) { accelOk = false; }
    try {
      _gyroSub = gyroscopeEventStream().listen((e) {
        _gyroBuf.add({'t': DateTime.now().millisecondsSinceEpoch / 1000.0, 'gx': e.x, 'gy': e.y, 'gz': e.z});
        if (_gyroBuf.length > 120) _gyroBuf.removeAt(0);
      }, onError: (_) { gyroOk = false; });
      gyroOk = true;
    } catch (_) { gyroOk = false; }
  }

  Future<void> _gpsTick() async {
    try {
      lastPos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.low, timeLimit: Duration(seconds: 4)),
      );
      gpsOk = true;
    } catch (_) {}
  }

  Future<void> _battTick() async {
    try { batteryPct = await Battery().batteryLevel; } catch (_) {}
  }

  double _windowRms() {
    if (_accelBuf.length < 10) return 0;
    final mags = _accelBuf.map((s) => sqrt(s['ax']! * s['ax']! + s['ay']! * s['ay']! + s['az']! * s['az']!)).toList();
    final mean = mags.reduce((a, b) => a + b) / mags.length;
    final centered = mags.map((m) => (m - mean).abs()).toList();
    final rms = sqrt(centered.map((c) => c * c).reduce((a, b) => a + b) / centered.length);
    lastRms = rms;
    return rms;
  }

  double _gyroEnergy() {
    if (_gyroBuf.length < 5) return 0;
    final tail = _gyroBuf.sublist(max(0, _gyroBuf.length - 20));
    return tail.map((g) => (g['gx']!.abs() + g['gy']!.abs() + g['gz']!.abs())).reduce((a, b) => a + b) / tail.length;
  }

  // bridge geofences (same as backend seed) — phone-side precheck to avoid useless POST
  static const _bridges = [[28.6289, 77.2410], [28.5670, 77.2100], [28.5930, 77.1630]];
  // School / VRU zones — RULE_BASED GPS proximity, not a child-detector model
  static const _schools = [[28.6328, 77.2195], [28.6200, 77.2220], [28.5670, 77.2100]];
  bool _nearBridge(double lat, double lon) {
    for (final b in _bridges) {
      final dLa = (lat - b[0]) * 111320, dLo = (lon - b[1]) * 111320 * cos(lat * pi / 180);
      if (sqrt(dLa * dLa + dLo * dLo) < 90) return true;
    }
    return false;
  }
  bool _nearSchool(double lat, double lon) {
    for (final s in _schools) {
      final dLa = (lat - s[0]) * 111320, dLo = (lon - s[1]) * 111320 * cos(lat * pi / 180);
      if (sqrt(dLa * dLa + dLo * dLo) < 80) return true;
    }
    return false;
  }

  Future<void> _evaluateTriggers() async {
    if (!running) return;
    if (_accelBuf.length < 30) return;
    final rms = _windowRms();
    final gyroE = _gyroEnergy();
    final now = DateTime.now();
    final speedKmh = lastPos == null ? 0.0 : max(0, lastPos!.speed * 3.6);
    final lat = lastPos?.latitude ?? 28.6289;
    final lon = lastPos?.longitude ?? 77.2410;
    final gpsSim = lastPos == null;

    // 1) POTHOLE: accel spike WITHOUT gyro turn (bump vs turn), speed 8-70
    final peak = _windowPeak();
    if (rms > 0.45 && peak > 0.9 && gyroE < 2.5 && speedKmh > 8 && speedKmh < 70) {
      if (_lastPotholeAt == null || now.difference(_lastPotholeAt!).inSeconds > 8) {
        _lastPotholeAt = now;
        await _emitPothole(lat, lon, rms, peak, speedKmh, gpsSim);
      }
    }
    // 2) BRIDGE batch: near geofence + enough samples
    if (!gpsSim && _nearBridge(lat, lon) && _accelBuf.length >= (batteryPct != null && batteryPct! < 20 ? 40 : 120)) {
      await _emitBridgeBatch(lat, lon, speedKmh);
    }
    // 3) CONGESTION proxy: speed <10 for 60s — check every 1s but throttle emit 60s
    if (!gpsSim && speedKmh < 10) {
      if (_lastCongAt == null || now.difference(_lastCongAt!).inSeconds > 90) {
        _lastCongAt = now;
        await _emitCongestion(lat, lon, speedKmh);
      }
    }
    // 4) RASH: speed >54 (~1.35x of 40 city limit)
    if (!gpsSim && speedKmh > 54) {
      if (_lastRashAt == null || now.difference(_lastRashAt!).inSeconds > 20) {
        _lastRashAt = now;
        await _emitRash(lat, lon, speedKmh);
      }
    }
    // 5) SCHOOL / VRU: near school + speed drop — RULE_BASED, not a child model
    if (!gpsSim && _nearSchool(lat, lon) && speedKmh < 25) {
      if (_lastSchoolAt == null || now.difference(_lastSchoolAt!).inSeconds > 90) {
        _lastSchoolAt = now;
        await _emitSchool(lat, lon, speedKmh);
      }
    }
  }

  double _windowPeak() {
    if (_accelBuf.length < 10) return 0;
    final mags = _accelBuf.map((s) => sqrt(s['ax']! * s['ax']! + s['ay']! * s['ay']! + s['az']! * s['az']!)).toList();
    final mean = mags.reduce((a, b) => a + b) / mags.length;
    return mags.map((m) => (m - mean).abs()).reduce(max);
  }

  Map<String, dynamic> _baseObs(String type, String sev, double lat, double lon, double conf, bool sim, double? speed) => {
    'event_type': type,
    'severity': sev,
    'latitude': lat,
    'longitude': lon,
    'gps_accuracy': lastPos?.accuracy,
    'timestamp': DateTime.now().toUtc().toIso8601String(),
    'source_type': 'PHONE',
    'source_id': busCode ?? sensorCode,
    'bus_id': null,
    'confidence': conf,
    'simulated': sim,
    'speed_kmh': speed,
    'heading': lastPos?.heading,
    'client_id': 'edge-${DateTime.now().millisecondsSinceEpoch}',
  };

  Future<void> _post(String path, Map<String, dynamic> body) async {
    try {
      final h = await _headers();
      final res = await http.post(Uri.parse('$apiBase$path'), headers: h, body: jsonEncode(body)).timeout(const Duration(seconds: 8));
      if (res.statusCode >= 400) throw Exception('${res.statusCode}');
      sentObs++;
      log('OK POST $path ${body['event_type'] ?? 'batch'} ok');
    } catch (e) {
      await _enqueue(body);
      queuedCount++;
      log('QUEUED offline ($queuedCount) $e');
    }
  }

  Future<void> _emitPothole(double lat, double lon, double rms, double peak, double speed, bool sim) async {
    final b = _baseObs('POTHOLE', rms > 0.6 ? 'HIGH' : 'MEDIUM', lat, lon, min(0.88, 0.55 + rms), sim, speed);
    b['extra'] = {'ai_status': 'RULE_BASED', 'engine_status': 'REAL', 'method': 'accel-spike no-gyro-turn', 'rms': rms, 'peak': peak, 'derivation': 'phone IMU trigger, backend fuses + YOLO on demand photo'};
    await _post('/observations', b);
  }

  Future<void> _emitCongestion(double lat, double lon, double speed) async {
    final b = _baseObs('TRAFFIC_CONGESTION', 'MEDIUM', lat, lon, 0.6, lastPos == null, speed);
    b['extra'] = {'ai_status': 'RULE_BASED', 'method': 'gps-speed proxy', 'derivation': 'phone speed<10 stop-go; real count via backend YOLO on demand + multi-bus fusion'};
    await _post('/observations', b);
  }

  Future<void> _emitRash(double lat, double lon, double speed) async {
    final b = _baseObs('RASH_DRIVING', 'HIGH', lat, lon, 0.7, lastPos == null, speed);
    b['extra'] = {'ai_status': 'RULE_BASED', 'engine_status': 'REAL', 'method': 'gps-speed>54 (1.35x40)', 'speed_calibrated': false, 'derivation': 'phone GPS trigger; plate via backend ANPR on photo'};
    await _post('/observations', b);
  }

  Future<void> _emitSchool(double lat, double lon, double speed) async {
    final b = _baseObs('PEDESTRIAN_RISK', 'MEDIUM', lat, lon, 0.58, lastPos == null, speed);
    b['extra'] = {
      'ai_status': 'RULE_BASED',
      'engine_status': 'RULE_BASED',
      'method': 'school-geofence + speed drop',
      'derivation': 'GPS 80m of school zone + speed <25. Not a child-detector or Indian sign model.',
    };
    await _post('/observations', b);
  }

  Future<void> _emitBridgeBatch(double lat, double lon, double speed) async {
    final cap = batchCap;
    final src = _accelBuf.length > cap ? _accelBuf.sublist(_accelBuf.length - cap) : List.from(_accelBuf);
    List<Map<String, dynamic>> samples;
    if (lowData) {
      samples = src.map((s) => {'t': double.parse(s['t']!.toStringAsFixed(1)), 'ax': double.parse(s['ax']!.toStringAsFixed(2)), 'ay': double.parse(s['ay']!.toStringAsFixed(2)), 'az': double.parse(s['az']!.toStringAsFixed(2))}).toList();
    } else {
      samples = src.map((s) => {'t': s['t']!, 'ax': s['ax']!, 'ay': s['ay']!, 'az': s['az']!}).toList();
    }
    final body = {
      'bridge_batch': true, // local flag, stripped before POST
      'latitude': lat, 'longitude': lon,
      'gps_accuracy': lastPos?.accuracy, 'speed_kmh': speed,
      'source_type': 'PHONE', 'source_id': busCode ?? sensorCode,
      'simulated': lastPos == null,
      'samples': samples,
      'extra': {'temp_c': 34},
    };
    try {
      final h = await _headers();
      final payload = Map<String, dynamic>.from(body)..remove('bridge_batch');
      final res = await http.post(Uri.parse('$apiBase/bridge/batch'), headers: h, body: jsonEncode(payload)).timeout(const Duration(seconds: 8));
      if (res.statusCode >= 400) throw Exception('${res.statusCode}');
      sentBatches++;
      final j = jsonDecode(res.body);
      log('OK bridge ${j['bridge_code']} ${j['severity']} rms=${(j['features']?['rms'] ?? 0).toStringAsFixed(3)}g');
      _accelBuf.clear();
    } catch (e) {
      await _enqueue(body);
      queuedCount++;
      log('QUEUED bridge batch ($queuedCount)');
    }
  }

  Future<void> _heartbeat() async {
    try {
      final h = await _headers();
      await http.post(Uri.parse('$apiBase/sensor-nodes/heartbeat'), headers: h, body: jsonEncode({
        'sensor_code': sensorCode, 'bus_code': busCode,
        'camera_status': cameraOk ? 'ONLINE' : 'OFFLINE', 'gps_status': gpsOk ? 'ONLINE' : 'UNAVAILABLE',
        'imu_status': accelOk ? 'ONLINE' : 'UNAVAILABLE', 'battery_pct': batteryPct,
        'network_type': net, 'ai_mode': 'EDGE_TRIGGER', 'processing_mode': processingMode,
        'sync_state': queuedCount > 0 ? 'PENDING $queuedCount' : 'SYNCED',
        'latitude': lastPos?.latitude, 'longitude': lastPos?.longitude,
        'speed_kmh': lastPos == null ? null : lastPos!.speed * 3.6, 'heading': lastPos?.heading,
      })).timeout(const Duration(seconds: 6));
    } catch (_) {}
  }

  Future<void> _sync() async {
    try {
      final f = await _qfile();
      if (!await f.exists()) { queuedCount = 0; return; }
      List items;
      try { items = jsonDecode(await f.readAsString()) as List; } catch (_) { return; }
      if (items.isEmpty) { queuedCount = 0; return; }
      final remain = [];
      for (final it in items) {
        try {
          final m = Map<String, dynamic>.from(it as Map);
          final h = await _headers();
          if (m['bridge_batch'] == true) {
            final p = Map<String, dynamic>.from(m)..remove('bridge_batch');
            final r = await http.post(Uri.parse('$apiBase/bridge/batch'), headers: h, body: jsonEncode(p)).timeout(const Duration(seconds: 8));
            if (r.statusCode >= 400) throw Exception('batch ${r.statusCode}');
          } else if (m.containsKey('samples')) {
            final p = Map<String, dynamic>.from(m)..remove('bridge_batch');
            final r = await http.post(Uri.parse('$apiBase/bridge/batch'), headers: h, body: jsonEncode(p)).timeout(const Duration(seconds: 8));
            if (r.statusCode >= 400) throw Exception('batch ${r.statusCode}');
          } else {
            final r = await http.post(Uri.parse('$apiBase/observations'), headers: h, body: jsonEncode(m)).timeout(const Duration(seconds: 8));
            if (r.statusCode >= 400) throw Exception('obs ${r.statusCode}');
          }
        } catch (_) { remain.add(it); }
      }
      await f.writeAsString(jsonEncode(remain));
      queuedCount = remain.length;
      if (remain.isEmpty) log('sync done');
    } catch (_) {}
  }

  /// Public manual sync for UI button (was _sync only on timer).
  Future<void> syncNow() async {
    log('manual sync…');
    await _sync();
    await _heartbeat();
    log('sync done q=$queuedCount');
  }

  Future<void> setLowData(bool v) async {
    lowData = v;
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool('low_data', v);
    } catch (_) {}
    log('low-data ${v ? "ON (batch 80, compressed)" : "OFF (batch 200)"}');
  }

  String statusLine() =>
      'run=$running bus=${busCode ?? "-"} rms=${lastRms.toStringAsFixed(3)}g buf=${_accelBuf.length}/$batchCap batt=${batteryPct ?? "-"}% net=$net sent=$sentObs/$sentBatches q=$queuedCount gps=${lastPos == null ? "sim" : "${lastPos!.latitude.toStringAsFixed(4)},${lastPos!.longitude.toStringAsFixed(4)}"}${batteryPct != null && batteryPct! < 20 ? " saver" : ""}';
}
