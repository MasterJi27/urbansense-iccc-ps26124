import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:battery_plus/battery_plus.dart';
import 'package:camera/camera.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'edge/edge_console.dart';
import 'edge/edge_service.dart';
import 'field_web_lens.dart';

const apiBase = String.fromEnvironment('API_BASE', defaultValue: 'https://app-urbansense-yngmbk.azurewebsites.net');

/// IMU / QR-camera plugins are phone-first. Windows desktop must not call them.
bool get kPhoneSensors => !Platform.isWindows && !Platform.isLinux && !Platform.isMacOS;

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (details) {
    if (details.exception is MissingPluginException) return;
    FlutterError.presentError(details);
  };
  runApp(const SadakSaarthiApp());
}

class SadakSaarthiApp extends StatelessWidget {
  const SadakSaarthiApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SadakSaarthi',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF070B12),
        colorScheme: const ColorScheme.dark(primary: Color(0xFF3EE0B4)),
      ),
      home: const Gate(),
    );
  }
}

class Session {
  static String? token;
  static String? role;
  static String? name;
  static String? userId;
  static String sensorCode = 'NODE-PHONE-01';
  static String? sensorId;
  static String? busCode;
  static String? busId;
  static String? tripId;
}

Future<Map<String, dynamic>> api(String path, {String method = 'GET', Map<String, dynamic>? body}) async {
  final uri = Uri.parse('$apiBase$path');
  final headers = <String, String>{'Content-Type': 'application/json'};
  if (Session.token != null) headers['Authorization'] = 'Bearer ${Session.token}';
  late http.Response res;
  if (method == 'POST') {
    res = await http.post(uri, headers: headers, body: jsonEncode(body ?? {}));
  } else if (method == 'PATCH') {
    res = await http.patch(uri, headers: headers, body: jsonEncode(body ?? {}));
  } else {
    res = await http.get(uri, headers: headers);
  }
  if (res.statusCode >= 400) {
    throw Exception('${res.statusCode} ${res.body}');
  }
  return jsonDecode(res.body) as Map<String, dynamic>;
}

Future<List<dynamic>> apiList(String path) async {
  final uri = Uri.parse('$apiBase$path');
  final headers = <String, String>{};
  if (Session.token != null) headers['Authorization'] = 'Bearer ${Session.token}';
  final res = await http.get(uri, headers: headers);
  if (res.statusCode >= 400) throw Exception(res.body);
  return jsonDecode(res.body) as List<dynamic>;
}

class OfflineQueue {
  static Future<File> _file() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/pending_observations.json');
  }

  static Future<List<Map<String, dynamic>>> load() async {
    final f = await _file();
    if (!await f.exists()) return [];
    final data = jsonDecode(await f.readAsString()) as List<dynamic>;
    return data.cast<Map<String, dynamic>>();
  }

  static Future<void> save(List<Map<String, dynamic>> items) async {
    final f = await _file();
    await f.writeAsString(jsonEncode(items));
  }

  static Future<void> enqueue(Map<String, dynamic> item) async {
    final items = await load();
    items.add(item);
    await save(items);
  }
}

class Gate extends StatefulWidget {
  const Gate({super.key});
  @override
  State<Gate> createState() => _GateState();
}

class _GateState extends State<Gate> {
  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final p = await SharedPreferences.getInstance();
    Session.token = p.getString('token');
    Session.role = p.getString('role');
    Session.busCode = p.getString('bus');
    if (Session.token != null && mounted) {
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeShell()));
    }
  }

  @override
  Widget build(BuildContext context) => const LoginPage();
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final email = TextEditingController(text: 'operator@urbansense.local');
  final pass = TextEditingController(text: 'UrbanSense@2026');
  String? err;
  bool loading = false;

  @override
  void dispose() {
    email.dispose();
    pass.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    setState(() {
      loading = true;
      err = null;
    });
    try {
      final data = await api('/auth/login', method: 'POST', body: {'email': email.text, 'password': pass.text});
      Session.token = data['access_token'] as String;
      Session.role = data['role'] as String;
      Session.name = data['full_name'] as String;
      Session.userId = data['user_id'] as String;
      final p = await SharedPreferences.getInstance();
      await p.setString('token', Session.token!);
      await p.setString('role', Session.role!);
      if (!mounted) return;
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeShell()));
    } catch (e) {
      setState(() => err = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('SADAKSAARTHI', style: TextStyle(fontSize: 24, letterSpacing: 2, color: Color(0xFF3EE0B4))),
            const SizedBox(height: 8),
            const Text('Phone edge — IMU+GPS, no YOLO, no video', textAlign: TextAlign.center),
            TextField(controller: email, decoration: const InputDecoration(labelText: 'Email')),
            TextField(controller: pass, obscureText: true, decoration: const InputDecoration(labelText: 'Password')),
            if (err != null) Text(err!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 12),
            FilledButton(onPressed: loading ? null : _login, child: Text(loading ? '…' : 'Login')),
          ],
        ),
      ),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int tab = 0;
  @override
  Widget build(BuildContext context) {
    final inspector = Session.role == 'INSPECTOR' || Session.role == 'ADMIN' || Session.role == 'SUPER_ADMIN';
    final pages = [
      const EdgeConsole(),
      const SensorHome(),
      const FieldWebLens(),
      if (inspector) const InspectorHome(),
      const EventsList(),
    ];
    return Scaffold(
      body: pages[tab.clamp(0, pages.length - 1)],
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [
          const NavigationDestination(icon: Icon(Icons.bolt), label: 'Edge'),
          const NavigationDestination(icon: Icon(Icons.sensors), label: 'Node'),
          const NavigationDestination(icon: Icon(Icons.videocam), label: 'Lens'),
          if (inspector) const NavigationDestination(icon: Icon(Icons.badge), label: 'Inspector'),
          const NavigationDestination(icon: Icon(Icons.list), label: 'Events'),
        ],
      ),
    );
  }
}

class DeviceCap {
  String mode = 'CAPTURE_AND_SENSOR';
  int ramGuessMb = 4096;
  String recommend = 'LOW / CAPTURE_AND_SENSOR';
}

class SensorHome extends StatefulWidget {
  const SensorHome({super.key});
  @override
  State<SensorHome> createState() => _SensorHomeState();
}

class _SensorHomeState extends State<SensorHome> {
  String gps = 'UNKNOWN';
  String imu = 'UNKNOWN';
  String net = 'UNKNOWN';
  String camera = 'UNKNOWN';
  int? battery;
  int pending = 0;
  String sync = 'IDLE';
  String ai = 'SIMULATION';
  DeviceCap cap = DeviceCap();
  StreamSubscription? accSub;
  Timer? hb;
  // Squad Battery — adaptive sampling (battery every 30s)
  Timer? _batteryTimer;
  StreamSubscription<BatteryState>? _batterySub;
  final Battery _battery = Battery();
  // 26124.5 SHM crowd — accel buffer for bridge batch
  bool shmArmed = true;
  int shmCount = 0;
  List<Map<String, dynamic>> shmBuf = [];
  String shmStatus = 'SHM idle';
  double shmLastRms = 0;
  // Joint photo — evidence_url for Work Order (offline queue)
  String? _jointPhotoPath;
  String? _jointEvidenceUrl;
  String? _lastBridgeCode;
  bool _jointPhotoQueued = false;
  // Squad Practical Low-data — toggles (minimal)
  bool lowData = false;
  bool useHindi = false;
  String _t(String en, String hi) => useHindi ? hi : en;
  // Battery adaptive caps: <20% => 40, 20-50% => 80, >50% => 200 (or lowData 80)
  int get _batchCap {
    if (battery != null && battery! < 20) return 40;
    if (battery != null && battery! <= 50) return 80;
    return lowData ? 80 : 200;
  }
  int get _accelCap {
    if (battery != null && battery! < 20) return 40;
    if (battery != null && battery! <= 50) return 80;
    return lowData ? 80 : 200;
  }
  int get _autoEmitTrigger {
    if (battery != null && battery! < 20) return 40;
    if (battery != null && battery! <= 50) return 80;
    return lowData ? 80 : 180;
  }
  int get _autoEmitMinBuf {
    if (battery != null && battery! < 20) return 30;
    if (battery != null && battery! <= 50) return 50;
    return lowData ? 50 : 120;
  }

  @override
  void initState() {
    super.initState();
    _loadPrefs();
    _boot();
  }

  Future<void> _loadPrefs() async {
    try {
      final p = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() {
        lowData = p.getBool('low_data') ?? false;
        useHindi = p.getBool('use_hindi') ?? false;
      });
    } catch (_) {}
  }

  Future<void> _savePrefs() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool('low_data', lowData);
      await p.setBool('use_hindi', useHindi);
    } catch (_) {}
  }

  // low-data: compress JSON — reduces batch 200→80, rounds values — battery adaptive 40/80/200
  List<Map<String, dynamic>> _compressedSamples() {
    final cap = _batchCap;
    final src = shmBuf.length > cap ? shmBuf.sublist(shmBuf.length - cap) : shmBuf;
    if (!lowData) return List.from(src);
    return src
        .map((s) => {
              't': double.parse((s['t'] as double).toStringAsFixed(1)),
              'ax': double.parse((s['ax'] as double).toStringAsFixed(2)),
              'ay': double.parse((s['ay'] as double).toStringAsFixed(2)),
              'az': double.parse((s['az'] as double).toStringAsFixed(2)),
            })
        .toList();
  }

  @override
  void dispose() {
    accSub?.cancel();
    hb?.cancel();
    _batteryTimer?.cancel();
    _batterySub?.cancel();
    super.dispose();
  }

  Future<void> _boot() async {
    try {
      battery = await _battery.batteryLevel;
      if (mounted) setState(() => shmStatus = 'SHM idle • batt ${battery ?? "n/a"}%');
    } catch (_) {}
    // battery listener — updates battery % and shmStatus on state change
    try {
      _batterySub = _battery.onBatteryStateChanged.listen((BatteryState state) async {
        try {
          final lvl = await _battery.batteryLevel;
          if (!mounted) return;
          setState(() {
            battery = lvl;
            shmStatus = 'SHM ${_accelCap < 200 ? "low-batt " : ""}buffering ${shmBuf.length}/$_accelCap • batt $battery% • rms ${shmLastRms.toStringAsFixed(3)}g${shmAutoEnabled ? " • auto" : ""}${lowData ? " • low-data" : ""}';
          });
        } catch (_) {}
      });
    } catch (_) {}
    // battery poll every 30s — adaptive caps 40/80/200
    _batteryTimer = Timer.periodic(const Duration(seconds: 30), (_) async {
      try {
        final lvl = await _battery.batteryLevel;
        if (!mounted) return;
        setState(() {
          battery = lvl;
          // update shmStatus with battery % (keep existing status but inject batt)
          if (shmBuf.isNotEmpty) {
            shmStatus = 'SHM buffering ${shmBuf.length}/$_accelCap • batt $battery% • rms ${shmLastRms.toStringAsFixed(3)}g${shmAutoEnabled ? " • auto" : ""}${lowData ? " • low-data" : ""}';
          } else {
            shmStatus = 'SHM idle • batt $battery%';
          }
        });
      } catch (_) {}
    });
    try {
      final c = await Connectivity().checkConnectivity();
      net = c.map((e) => e.name).join(',');
    } catch (_) {
      net = 'UNAVAILABLE';
    }
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      gps = enabled ? 'ONLINE' : 'UNAVAILABLE';
    } catch (_) {
      gps = 'UNAVAILABLE';
    }
    if (!kPhoneSensors) {
      imu = 'UNAVAILABLE';
    } else {
      try {
        accSub = accelerometerEventStream().listen(
          (e) {
            if (mounted) setState(() => imu = 'ONLINE');
            _onAccel(e);
          },
          onError: (_) {
            if (mounted) setState(() => imu = 'UNAVAILABLE');
          },
        );
      } catch (_) {
        imu = 'UNAVAILABLE';
      }
    }
    try {
      final cams = await availableCameras();
      camera = cams.isEmpty ? 'OFFLINE' : 'ONLINE';
    } catch (_) {
      camera = 'OFFLINE';
    }
    final q = await OfflineQueue.load();
    pending = q.length;
    cap.mode = (battery != null && battery! < 25) ? 'CAPTURE_AND_SENSOR' : 'LIGHTWEIGHT_EDGE_AI';
    cap.recommend = camera == 'ONLINE' ? cap.mode : 'CAPTURE_AND_SENSOR';
    setState(() {});
    hb = Timer.periodic(const Duration(seconds: 12), (_) => _heartbeat());
    _heartbeat();
    _trySync();
  }

  Future<void> _heartbeat() async {
    Position? pos;
    try {
      pos = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.low));
      gps = 'ONLINE';
    } catch (_) {}
    try {
      await api('/sensor-nodes/heartbeat', method: 'POST', body: {
        'sensor_code': Session.sensorCode,
        'bus_code': Session.busCode,
        'camera_status': camera,
        'gps_status': gps,
        'imu_status': imu,
        'battery_pct': battery,
        'network_type': net,
        'ai_mode': ai,
        'processing_mode': cap.recommend.contains('EDGE') ? 'LIGHTWEIGHT_EDGE_AI' : 'CAPTURE_AND_SENSOR',
        'sync_state': sync,
        'latitude': pos?.latitude,
        'longitude': pos?.longitude,
        'speed_kmh': pos == null ? null : (pos.speed * 3.6),
        'heading': pos?.heading,
      });
    } catch (_) {}
  }

  Future<void> _trySync() async {
    final items = await OfflineQueue.load();
    if (items.isEmpty) {
      setState(() {
        sync = 'ALL EVENTS SYNCED';
        pending = 0;
      });
      return;
    }
    setState(() => sync = 'SYNCING 0/${items.length}');
    final remain = <Map<String, dynamic>>[];
    var ok = 0;
    for (final item in items) {
      try {
        // SHM batches go to /bridge/batch, rest to /observations
        if (item['bridge_batch'] == true) {
          final b = Map<String, dynamic>.from(item)..remove('bridge_batch');
          await api('/bridge/batch', method: 'POST', body: b);
        } else if (item['work_order_evidence'] == true) {
          final wid = item['work_order_id'];
          if (wid != null) {
            var evUrl = (item['evidence_url'] as String?) ?? '';
            // Ensure evidence_url carries EXIF GPS even if older queue lacks query — embed from extra/lat lon
            if (!evUrl.contains('lat=') && item['latitude'] != null) {
              final ts = item['timestamp'] as String? ?? DateTime.now().toUtc().toIso8601String();
              final sep = evUrl.contains('?') ? '&' : '?';
              evUrl = '$evUrl${sep}lat=${item['latitude']}&lon=${item['longitude']}&t=${Uri.encodeComponent(ts)}';
              if (item['gps_accuracy'] != null) evUrl = '$evUrl&acc=${item['gps_accuracy']}';
              if (item['bridge_code'] != null) evUrl = '$evUrl&bridge=${Uri.encodeComponent(item['bridge_code'] as String)}';
            } else if (!evUrl.contains('t=') && item['timestamp'] != null) {
              final sep = evUrl.contains('?') ? '&' : '?';
              evUrl = '$evUrl${sep}t=${Uri.encodeComponent(item['timestamp'] as String)}';
            }
            // also send extra gps via notes suffix if backend only stores notes/evidence_url
            var notes = (item['notes'] as String?) ?? 'Joint photo from bridge SHM';
            if (item['latitude'] != null && !notes.contains('GPS')) {
              notes = '$notes [GPS ${item['latitude']},${item['longitude']} acc=${item['gps_accuracy'] ?? "n/a"}m @ ${item['timestamp'] ?? ""}]';
            }
            await api('/work-orders/$wid/repair', method: 'POST', body: {
              'notes': notes,
              'evidence_url': evUrl,
            });
          } else {
            // No WO bound yet — keep queued as evidence_url for next Work Order (offline queue intact)
            throw Exception('no work_order_id — keep queued');
          }
        } else {
          await api('/observations', method: 'POST', body: item);
        }
        ok++;
        setState(() => sync = 'SYNCING $ok/${items.length}');
      } catch (_) {
        remain.add(item);
      }
    }
    await OfflineQueue.save(remain);
    setState(() {
      pending = remain.length;
      sync = remain.isEmpty ? 'ALL EVENTS SYNCED' : 'OFFLINE pending ${remain.length}';
    });
  }

  // 26124.5 SHM helpers — battery adaptive: <20% cap 40, 20-50 cap 80, >50 cap 200
  void _onAccel(dynamic e) {
    try {
      final ax = (e.x as num).toDouble();
      final ay = (e.y as num).toDouble();
      final az = (e.z as num).toDouble();
      if (!shmArmed) return;
      shmBuf.add({'t': DateTime.now().millisecondsSinceEpoch/1000.0, 'ax': ax, 'ay': ay, 'az': az});
      final cap = _accelCap;
      if (shmBuf.length > cap) shmBuf.removeRange(0, shmBuf.length - cap);
      if (shmBuf.length > 420) shmBuf.removeAt(0);
      if (shmBuf.length % 20 == 0) {
        final mags = shmBuf.map((s)=> (s['ax']*s['ax']+s['ay']*s['ay']+s['az']*s['az']) as double).map((v)=> v>0? math.sqrt(v):0).toList();
        final mean = mags.reduce((a,b)=>a+b)/mags.length;
        final centered = mags.map((m)=> (m-mean).abs()).toList();
        final rms = math.sqrt(centered.map((c)=>c*c).reduce((a,b)=>a+b)/centered.length);
        final delta = (rms - shmLastRms).abs();
        shmLastRms = rms;
        // Lightweight throttle: only rebuild when rms shifts >0.05g
        if (delta > 0.05 && mounted) setState(() => shmStatus = 'SHM buffering ${shmBuf.length}/$cap • batt ${battery ?? "n/a"}% • rms ${rms.toStringAsFixed(3)}g${shmAutoEnabled?" • auto":""}${lowData?" • low-data":""}${battery != null && battery! < 20 ? " • batt-low" : ""}');
        _maybeAutoEmit();
      }
    } catch (_) {}
  }

  bool shmAutoEnabled = true;
  Position? lastPos;

  Future<void> _maybeAutoEmit() async {
    final minBuf = _autoEmitMinBuf;
    final trigger = _autoEmitTrigger;
    if (!shmAutoEnabled || shmBuf.length < minBuf) return;
    Position? pos;
    try { pos = await Geolocator.getCurrentPosition(); lastPos=pos; } catch (_) { pos=lastPos; }
    if (pos==null) return;
    // crude geofence check for 3 bridges (avoid backend round-trip)
    const bridges = [[28.6289,77.2410],[28.5670,77.2100],[28.5930,77.1630]];
    bool near = bridges.any((b)=> _dist(pos!.latitude,pos.longitude,b[0],b[1]) < 80);
    if (!near) return;
    if (shmBuf.length >= trigger) await _emitBridgeBatch();
  }

  double _dist(double la1,double lo1,double la2,double lo2){
    const R=6371000; final dLa=(la2-la1)*3.14159/180; final dLo=(lo2-lo1)*3.14159/180;
    final a = math.sin(dLa/2)*math.sin(dLa/2) + math.cos(la1*3.14159/180)*math.cos(la2*3.14159/180)*math.sin(dLo/2)*math.sin(dLo/2);
    return 2*R*math.asin(math.sqrt(a));
  }

  Future<void> _emitBridgeBatch() async {
    if (shmBuf.length < 30) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Need ~1s of vibration — drive on bridge')));
      return;
    }
    Position? pos;
    try { pos = await Geolocator.getCurrentPosition(); lastPos=pos; } catch (_) { pos=lastPos; }
    final batch = {
      'bridge_batch': true,
      'latitude': pos?.latitude ?? 28.6289,
      'longitude': pos?.longitude ?? 77.2410,
      'gps_accuracy': pos?.accuracy,
      'speed_kmh': pos==null? null: pos.speed*3.6,
      'source_type': 'PHONE',
      'source_id': Session.busCode ?? Session.sensorCode,
      'sensor_id': Session.sensorId,
      'bus_id': Session.busId,
      'simulated': pos==null,
      'samples': _compressedSamples(),
      'extra': {'temp_c': 34},
    };
    try {
      final res = await api('/bridge/batch', method: 'POST', body: Map<String,dynamic>.from(batch)..remove('bridge_batch'));
      _lastBridgeCode = res['bridge_code'] as String? ?? _lastBridgeCode;
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${res['bridge_code'] ?? 'Bridge'}: ${res['event_type']} ${res['severity']} rms ${res['features']?['rms']?.toStringAsFixed(3) ?? ''}g')));
      shmBuf.clear();
      setState(() { shmCount++; shmStatus = 'SHM sent ${shmCount} batches • batt ${battery ?? "n/a"}%'; });
    } catch (_) {
      await OfflineQueue.enqueue(batch);
      final q = await OfflineQueue.load();
      if (mounted) setState(() => pending = q.length);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Offline — SHM batch queued')));
    }
  }

  Future<void> _attachJointPhoto() async {
    String? capturedPath;
    String? evidenceUrl;
    // EXIF GPS — capture location + UTC time before shutter for embedding
    Position? snapPos;
    final isoTime = DateTime.now().toUtc().toIso8601String();
    try {
      snapPos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high, timeLimit: const Duration(seconds: 4));
      lastPos = snapPos;
    } catch (_) {
      snapPos = lastPos;
    }
    // Try camera plugin if available, else placeholder (file picker placeholder)
    if (camera == 'ONLINE') {
      try {
        final cams = await availableCameras();
        if (cams.isNotEmpty) {
          final ctrl = CameraController(cams.first, ResolutionPreset.medium, enableAudio: false);
          await ctrl.initialize();
          final XFile file = await ctrl.takePicture();
          final dir = await getApplicationDocumentsDirectory();
          final target = File('${dir.path}/joint_${DateTime.now().millisecondsSinceEpoch}.jpg');
          await File(file.path).copy(target.path);
          capturedPath = target.path;
          await ctrl.dispose();
          if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Joint photo captured: ${target.path.split(Platform.pathSeparator).last}')));
        }
      } catch (e) {
        capturedPath = null;
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Camera error — using placeholder: $e')));
      }
    }
    // file picker placeholder fallback when camera unavailable or capture failed
    if (capturedPath == null) {
      try {
        final dir = await getApplicationDocumentsDirectory();
        final placeholder = File('${dir.path}/joint_placeholder_${DateTime.now().millisecondsSinceEpoch}.txt');
        final gpsTag = snapPos != null
            ? ' lat=${snapPos.latitude.toStringAsFixed(6)} lon=${snapPos.longitude.toStringAsFixed(6)} acc=${snapPos.accuracy?.toStringAsFixed(1) ?? "n/a"}'
            : ' lat=n/a lon=n/a';
        await placeholder.writeAsString('placeholder joint photo $isoTime bridge=${_lastBridgeCode ?? 'unknown'}$gpsTag EXIF GPS embedded');
        capturedPath = placeholder.path;
        if (mounted) {
          await showDialog<void>(
            context: context,
            builder: (_) => AlertDialog(
              title: const Text('Camera unavailable'),
              content: Text('Placeholder created:
${placeholder.path.split(Platform.pathSeparator).last}
$gpsTag

On device this would open file picker. Using placeholder file as evidence_url.'),
              actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
            ),
          );
        }
      } catch (_) {}
    }
    if (capturedPath != null) {
      // Embed GPS + time EXIF into evidence_url query (file://...?lat=&lon=&t=&acc=&bridge=) — minimal, no JPEG EXIF lib needed; dashboard parses and displays
      var baseUrl = 'file://$capturedPath';
      if (snapPos != null) {
        baseUrl = '$baseUrl?lat=${snapPos.latitude.toStringAsFixed(6)}&lon=${snapPos.longitude.toStringAsFixed(6)}&t=${Uri.encodeComponent(isoTime)}&acc=${snapPos.accuracy?.toStringAsFixed(1) ?? "n/a"}&bridge=${Uri.encodeComponent(_lastBridgeCode ?? "unknown")}';
      } else {
        baseUrl = '$baseUrl?t=${Uri.encodeComponent(isoTime)}&bridge=${Uri.encodeComponent(_lastBridgeCode ?? "unknown")}';
      }
      evidenceUrl = baseUrl;
      setState(() {
        _jointPhotoPath = capturedPath;
        _jointEvidenceUrl = evidenceUrl;
      });
      // queue as Work Order evidence — keep offline queue intact (distinct flag, never drops) — includes explicit GPS extra lat/lon
      final woEvidence = {
        'work_order_evidence': true,
        'evidence_url': evidenceUrl,
        'local_path': capturedPath,
        'latitude': snapPos?.latitude ?? lastPos?.latitude,
        'longitude': snapPos?.longitude ?? lastPos?.longitude,
        'gps_accuracy': snapPos?.accuracy,
        'bridge_code': _lastBridgeCode,
        'timestamp': isoTime,
        'source_id': Session.busCode ?? Session.sensorCode,
        'notes': 'Joint photo from bridge SHM',
        'extra': {
          'lat': snapPos?.latitude ?? lastPos?.latitude,
          'lon': snapPos?.longitude ?? lastPos?.longitude,
          'gps_accuracy': snapPos?.accuracy,
          'timestamp': isoTime,
          'bridge_code': _lastBridgeCode,
          'exif_gps': snapPos != null,
        },
      };
      await OfflineQueue.enqueue(woEvidence);
      final q = await OfflineQueue.load();
      setState(() {
        pending = q.length;
        _jointPhotoQueued = true;
        sync = 'OFFLINE pending ${q.length}';
        shmStatus = 'SHM idle • batt ${battery ?? "n/a"}% • joint photo queued ${evidenceUrl!.split(Platform.pathSeparator).last}';
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Queued as evidence_url for Work Order (offline queue ${q.length})')));
      _trySync();
    }
  }

  Future<void> _scanBus() async {
    final payload = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const QrScanPage()));
    if (payload == null) return;
    try {
      final found = await api('/qr/lookup?payload=${Uri.encodeQueryComponent(payload)}');
      if (found['found'] == true && found['kind'] == 'bus') {
        Session.busCode = found['code'] as String;
        Session.busId = found['id'] as String;
        await api('/sensor-nodes/bind', method: 'POST', body: {
          'sensor_code': Session.sensorCode,
          'bus_code': Session.busCode,
          'device_label': 'PHONE',
        });
        final p = await SharedPreferences.getInstance();
        await p.setString('bus', Session.busCode!);
        if (mounted) setState(() {});
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _trip(bool start) async {
    try {
      if (start) {
        final t = await api('/trips', method: 'POST', body: {'bus_id': Session.busId, 'simulated': false});
        Session.tripId = t['id'] as String;
      } else if (Session.tripId != null) {
        await api('/trips/${Session.tripId}/stop', method: 'POST');
        Session.tripId = null;
      }
      setState(() {});
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final isBound = Session.busCode != null;
    final isOnTrip = Session.tripId != null;
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Header — H-device status at a glance (bilingual)
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: const Color(0xFF0F1B2D), borderRadius: BorderRadius.circular(16), border: Border.all(color: const Color(0xFF1E2F4A))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Container(width:10,height:10,decoration: BoxDecoration(color: isOnTrip ? const Color(0xFF0BB98A) : Colors.amber, shape: BoxShape.circle)),
                const SizedBox(width:8),
                Text(isOnTrip ? _t('ON TRIP','ट्रिप पर') : _t('IDLE','निष्क्रिय'), style: const TextStyle(fontSize:13,letterSpacing:1.2,fontWeight:FontWeight.w700,color: Colors.white70)),
                const Spacer(),
                Container(padding: const EdgeInsets.symmetric(horizontal:8,vertical:4), decoration: BoxDecoration(color: const Color(0xFF0BB98A).withValues(alpha: 0.15), borderRadius: BorderRadius.circular(99)), child: Text(Session.sensorCode, style: const TextStyle(fontSize:12, fontFamily: 'monospace', color: Color(0xFF0BB98A)))),
              ]),
              const SizedBox(height:10),
              Text(Session.busCode ?? _t('UNBOUND — scan bus QR','अनबाउंड — बस QR स्कैन करें'), maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize:18,fontWeight:FontWeight.w800,color: isBound? Colors.white : Colors.white54)),
              const SizedBox(height:2),
              Text(isOnTrip ? _t('Trip ${Session.tripId!.substring(0,8)}…','ट्रिप ${Session.tripId!.substring(0,8)}…') : _t('No active trip','कोई सक्रिय ट्रिप नहीं'), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize:12,fontWeight:FontWeight.w600,color: Colors.white54)),
              const SizedBox(height:10),
              Container(padding: const EdgeInsets.symmetric(horizontal:10,vertical:6), decoration: BoxDecoration(color: pending>0 ? Colors.amber.withValues(alpha: 0.12) : const Color(0xFF0BB98A).withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8), border: Border.all(color: pending>0? Colors.amber.withValues(alpha: 0.3): const Color(0xFF0BB98A).withValues(alpha: 0.25))),
                child: Row(children:[Icon(pending>0? Icons.cloud_off: Icons.cloud_done, size:14,color: pending>0? Colors.amber: const Color(0xFF0BB98A)), const SizedBox(width:6), Expanded(child: Text(pending>0? _t('OFFLINE — $pending queued','ऑफलाइन — $pending कतार में'):_t('ALL EVENTS SYNCED','सभी इवेंट सिंक'), maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize:12,fontWeight:FontWeight.w700,color: pending>0? Colors.amber: const Color(0xFF0BB98A))))])),
            ]),
          ),
          const SizedBox(height: 10),
          // Settings — Low-data + Hindi toggles (minimal)
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFF111827), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF1E2F4A))),
            child: Column(children: [
              Row(children: [
                const Icon(Icons.data_saver_on, size:16, color: Color(0xFF0BB98A)),
                const SizedBox(width:8),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[
                  Text(_t('Low-data mode','कम डेटा मोड'), style: TextStyle(fontSize:13, fontWeight: FontWeight.w700, color: Colors.white)),
                  Text(_t('Batch 200→80, JSON compressed','बैच 200→80, JSON संपीड़ित'), style: TextStyle(fontSize:10, color: Colors.white54)),
                ])),
                Switch(value: lowData, onChanged: (v){ setState(()=> lowData=v); _savePrefs(); }, activeColor: const Color(0xFF0BB98A)),
              ]),
              const Divider(color: Color(0xFF1E2F4A), height:16),
              Row(children: [
                const Icon(Icons.language, size:16, color: Color(0xFF0BB98A)),
                const SizedBox(width:8),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[
                  Text(_t('Hindi labels','हिंदी लेबल'), style: TextStyle(fontSize:13, fontWeight: FontWeight.w700, color: Colors.white)),
                  Text(_t('Toggle English / हिंदी','अंग्रेज़ी / हिंदी बदलें'), style: TextStyle(fontSize:10, color: Colors.white54)),
                ])),
                Switch(value: useHindi, onChanged: (v){ setState(()=> useHindi=v); _savePrefs(); }, activeColor: const Color(0xFF0BB98A)),
              ]),
            ]),
          ),
          const SizedBox(height: 8),
          // Sensor grid — 6 chips as status tiles
          GridView.count(
            crossAxisCount: 3, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), mainAxisSpacing: 8, crossAxisSpacing: 8, childAspectRatio: 2.1,
            children: [
              _tile('GPS', gps, gps=='ONLINE'? const Color(0xFF0BB98A): Colors.white24),
              _tile('IMU', imu, imu=='ONLINE'? const Color(0xFF0BB98A): Colors.white24),
              _tile('CAM', camera, camera=='ONLINE'? const Color(0xFF0BB98A): Colors.white24),
              _tile('NET', net, net.contains('WIFI')||net.contains('4G')||net.contains('5G')? const Color(0xFF0BB98A): Colors.white24),
              _tile('BAT', '${battery ?? "n/a"}%', (battery??100) <20? Colors.redAccent: const Color(0xFF0BB98A)),
              _tile('AI', ai, ai.contains('EDGE')? const Color(0xFF0BB98A): Colors.white54),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFF111827), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF1E2F4A))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('DEVICE CAPABILITY', style: TextStyle(fontSize:11,letterSpacing:1.1,fontWeight:FontWeight.w700,color: Colors.white54)),
              const SizedBox(height:6),
              Row(children:[const Icon(Icons.memory, size:14,color: Color(0xFF0BB98A)), const SizedBox(width:6), Expanded(child: Text(cap.recommend, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize:13,fontWeight:FontWeight.w700,color: Colors.white)))]),
              const SizedBox(height:4),
              const Text('HIGH=EDGE_AI  •  MEDIUM=LIGHTWEIGHT  •  LOW=CAPTURE_ONLY', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize:11,color: Colors.white38)),
            ]),
          ),
          // 26124.5 SHM Bridge — crowd vibration v2 (bilingual + low-data)
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(12), border: Border.all(color: shmArmed? const Color(0xFF0BB98A).withValues(alpha:.35): Colors.white12)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[
              Row(children:[
                const Icon(Icons.vibration, size:14,color: Color(0xFF0BB98A)), const SizedBox(width:6),
                const Text('STRUCTURAL PULSE — screening (not prediction)', style: TextStyle(fontSize:10,letterSpacing:.9,fontWeight:FontWeight.w800,color: Colors.white70)),
                const Spacer(),
                Switch(value: shmArmed, onChanged: (v)=> setState(()=> shmArmed=v), activeColor: const Color(0xFF0BB98A)),
              ]),
              Row(children:[
                Text(_t('Auto on bridge','पुल पर ऑटो'), style: TextStyle(fontSize:10,color: Colors.white54)), const SizedBox(width:6),
                Switch(value: shmAutoEnabled, onChanged: (v)=> setState(()=> shmAutoEnabled=v), activeColor: const Color(0xFF0BB98A)),
                const Spacer(),
                Container(padding: const EdgeInsets.symmetric(horizontal:6,vertical:2), decoration: BoxDecoration(color: Colors.white10, borderRadius: BorderRadius.circular(6)), child: Text(shmStatus, style: const TextStyle(fontSize:10,color: Colors.white60, fontFamily: 'monospace'))),
              ]),
              if (lowData) Padding(padding: const EdgeInsets.only(top:4), child: Text(_t('Low-data: batch 80 (was 200), JSON compressed','कम डेटा: बैच 80 (पहले 200), JSON संपीड़ित'), style: TextStyle(fontSize:9, color: Color(0xFF0BB98A)))),
              const SizedBox(height:8),
              Row(children:[
                Expanded(child: FilledButton.icon(onPressed: _emitBridgeBatch, icon: const Icon(Icons.waves, size:16), label: Text(_t('SEND BRIDGE BATCH (${shmBuf.length})','ब्रिज बैच भेजें (${shmBuf.length})')), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0BB98A)))),
                const SizedBox(width:8),
                OutlinedButton(onPressed: ()=> setState(()=> shmBuf.clear()), child: Text(_t('Clear','साफ करें'))),
              ]),
              const SizedBox(height:8),
              // Joint photo capture — camera plugin else file picker placeholder; queues evidence_url for WO (offline queue intact)
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _attachJointPhoto,
                  icon: Icon(_jointPhotoPath == null ? Icons.camera_alt : Icons.check_circle, size:16, color: _jointPhotoQueued ? const Color(0xFF0BB98A) : Colors.white70),
                  label: Text(_jointPhotoPath == null ? _t('Attach Joint Photo','जॉइंट फोटो जोड़ें') : '${_t('Joint Photo:','जॉइंट फोटो:')} ${_jointPhotoPath!.split(Platform.pathSeparator).last}', style: TextStyle(fontSize:11, fontWeight: FontWeight.w700, color: _jointPhotoQueued ? const Color(0xFF0BB98A) : Colors.white70), overflow: TextOverflow.ellipsis),
                  style: OutlinedButton.styleFrom(side: BorderSide(color: _jointPhotoQueued ? const Color(0xFF0BB98A).withValues(alpha: 0.5) : Colors.white24), foregroundColor: Colors.white70),
                ),
              ),
              if (_jointEvidenceUrl != null) ...[
                const SizedBox(height:4),
                Text('${_t('evidence_url queued:','evidence_url कतार में:')} $_jointEvidenceUrl', style: const TextStyle(fontSize:9,color: Colors.white38, fontFamily: 'monospace'), maxLines:1, overflow: TextOverflow.ellipsis),
                const Text('EXIF GPS: lat/lon/time embedded in evidence_url ?lat=&lon=&t= + extra lat/lon', style: TextStyle(fontSize:9,color: Colors.white54, fontFamily: 'monospace')),
                if (_jointPhotoQueued) Text(_t('Offline queue intact — will attach to Work Order on sync','ऑफलाइन कतार सुरक्षित — वर्क ऑर्डर पर सिंक होगा'), style: TextStyle(fontSize:9,color: Color(0xFF0BB98A))),
              ],
              const SizedBox(height:4),
              Text(_t('Auto at 70m when ≥180 samples • drift → flag for inspection (not safety) • offline','70m पर ≥180 सैंपल पर ऑटो • ड्रिफ्ट → जांच के लिए फ्लैग (सुरक्षा नहीं) • ऑफलाइन'), style: TextStyle(fontSize:9,color: Colors.white30)),
            ]),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(onPressed: _scanBus, icon: const Icon(Icons.qr_code_scanner, size:18), label: const Text('SCAN QR — bind bus / asset / WO'), style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48))),
          const SizedBox(height: 8),
          Row(children:[
            Expanded(child: FilledButton.icon(onPressed: isBound && !isOnTrip ? ()=>_trip(true): null, icon: const Icon(Icons.play_arrow), label: const Text('START TRIP'), style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)))),
            const SizedBox(width:8),
            Expanded(child: OutlinedButton.icon(onPressed: isOnTrip ? ()=>_trip(false): null, icon: const Icon(Icons.stop), label: const Text('STOP'), style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)))),
          ]),
          const SizedBox(height: 8),
          OutlinedButton.icon(onPressed: _trySync, icon: const Icon(Icons.sync), label: Text(pending>0? 'SYNC NOW ($pending)':'SYNC NOW'), style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48))),
          const SizedBox(height:8),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const FieldWebLens())),
            icon: const Icon(Icons.videocam),
            label: const Text('ROAD LENS — same /field'),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48), backgroundColor: const Color(0xFF0BB98A)),
          ),
          const SizedBox(height: 8),
          const Text('IMU/GPS/SHM on this tab. Boxes live on Lens = Azure /field WebView, not a second YOLO.', style: TextStyle(fontSize:12,color: Colors.white38), textAlign: TextAlign.center),
        ],
      ),
    );
  }

  Widget _tile(String k, String v, Color c) => Container(
    padding: const EdgeInsets.symmetric(horizontal:8,vertical:8),
    decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(10), border: Border.all(color: c.withValues(alpha: 0.35))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children:[
      Text(k, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize:11,letterSpacing:.8,fontWeight:FontWeight.w700,color: Colors.white54)),
      const SizedBox(height:2),
      Text(v, style: TextStyle(fontSize:12,fontWeight:FontWeight.w700,color: c==Colors.white24||c==Colors.white54? Colors.white70: c, fontFamily: 'monospace'), maxLines:1, overflow: TextOverflow.ellipsis),
    ]),
  );
}

class SensorLive extends StatefulWidget {
  const SensorLive({super.key});
  @override
  State<SensorLive> createState() => _SensorLiveState();
}

class _SensorLiveState extends State<SensorLive> {
  CameraController? cam;
  String camStatus = 'CAMERA OFFLINE';
  Position? pos;
  String overlay = 'PATROL ARMED';
  double? ax;
  Timer? tick;
  Timer? patrolTick;
  StreamSubscription? accSub;
  bool _busyStill = false;
  DateTime? _lastStillAt;
  List<Map<String, dynamic>> boxes = [];

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    accSub?.cancel();
    tick?.cancel();
    patrolTick?.cancel();
    unawaited(EdgeService.I.stop());
    cam?.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    try {
      final cams = await availableCameras();
      if (cams.isNotEmpty) {
        cam = CameraController(cams.first, ResolutionPreset.medium, enableAudio: false);
        await cam!.initialize();
        camStatus = 'CAMERA LIVE';
        overlay = 'CAMERA LIVE — IMU stills. Road boxes: Lens tab /field';
        unawaited(EdgeService.I.start(apiBaseOverride: apiBase, busCodeOverride: Session.busCode));
        patrolTick = Timer.periodic(const Duration(seconds: 4), (_) => _patrolTick());
      }
    } catch (_) {
      camStatus = 'CAMERA OFFLINE';
    }
    try {
      pos = await Geolocator.getCurrentPosition();
    } catch (_) {}
    if (kPhoneSensors) {
      try {
        accSub = accelerometerEventStream().listen(
          (e) {
            if (mounted) setState(() => ax = e.x.abs() + e.y.abs() + e.z.abs());
          },
          onError: (_) {},
        );
      } catch (_) {}
    }
    tick = Timer.periodic(const Duration(seconds: 4), (_) async {
      try {
        pos = await Geolocator.getCurrentPosition();
      } catch (_) {}
      if (mounted) setState(() {});
    });
    if (mounted) setState(() {});
  }

  Future<void> _patrolTick() async {
    if (!mounted || _busyStill || cam == null || !cam!.value.isInitialized) return;
    final imuSpike = ax != null && ax! > 16;
    if (!imuSpike) return;
    final now = DateTime.now();
    if (_lastStillAt != null && now.difference(_lastStillAt!).inSeconds < 8) return;
    await _emit(patrol: true, trigger: 'imu');
  }

  void _applyDetections(Map<String, dynamic> j) {
    final extra = (j['event'] is Map) ? (j['event'] as Map)['extra'] : null;
    final raw = (j['detections'] as List?) ?? (extra is Map ? extra['detections'] as List? : null) ?? const [];
    boxes = raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    if (boxes.isNotEmpty) {
      final top = boxes.first;
      final pct = ((top['confidence'] as num?) ?? 0) * 100;
      overlay = '${top['klass'] ?? top['event_type']} ${pct.round()}% — Azure RDD';
    }
  }

  Future<void> _emit({bool forceOffline = false, bool patrol = false, String trigger = 'manual'}) async {
    if (_busyStill) return;
    _busyStill = true;
    final lat = pos?.latitude ?? 28.6328;
    final lon = pos?.longitude ?? 77.2195;
    final gpsOk = pos != null;
    final body = {
      'event_type': 'POTHOLE',
      'severity': 'HIGH',
      'latitude': lat,
      'longitude': lon,
      'gps_accuracy': pos?.accuracy,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'source_type': 'PHONE',
      'source_id': Session.busCode ?? Session.sensorCode,
      'bus_id': Session.busId,
      'confidence': 0.84,
      'simulated': !patrol,
      'speed_kmh': pos == null ? null : pos!.speed * 3.6,
      'heading': pos?.heading,
      'extra': {'ai': patrol ? 'PATROL' : 'SIMULATION', 'imu_mag': ax, 'gps_available': gpsOk, 'patrol_trigger': trigger},
      'client_id': 'local-${DateTime.now().millisecondsSinceEpoch}',
    };
    if (mounted) setState(() => overlay = patrol ? 'PATROL STILL ($trigger)' : 'MANUAL STILL');
    try {
    if (forceOffline) {
      await OfflineQueue.enqueue(body);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Queued offline')));
      return;
    }
    if (cam != null && cam!.value.isInitialized) {
      try {
        final shot = await cam!.takePicture();
        _lastStillAt = DateTime.now();
        final req = http.MultipartRequest('POST', Uri.parse('$apiBase/ingest/phone/still'));
        if (Session.token != null) req.headers['Authorization'] = 'Bearer ${Session.token}';
        req.fields['latitude'] = '$lat';
        req.fields['longitude'] = '$lon';
        if (pos?.accuracy != null) req.fields['gps_accuracy'] = '${pos!.accuracy}';
        req.fields['source_id'] = Session.busCode ?? Session.sensorCode;
        if (Session.busId != null) req.fields['bus_id'] = Session.busId!;
        if (pos?.heading != null) req.fields['heading'] = '${pos!.heading}';
        req.fields['speed_kmh'] = '${pos == null ? 0 : pos!.speed * 3.6}';
        req.fields['imu_mag'] = '$ax';
        req.fields['camera_bay'] = 'FRONT';
        req.files.add(await http.MultipartFile.fromPath('file', shot.path));
        final streamed = await req.send();
        if (streamed.statusCode >= 200 && streamed.statusCode < 300) {
          final res = await http.Response.fromStream(streamed);
          try {
            final j = jsonDecode(res.body) as Map<String, dynamic>;
            final ev = (j['event'] as Map?) ?? {};
            final created = j['created_event'] == true;
            final code = ev['public_code'] ?? '';
            final sources = ev['source_count'] ?? 1;
            if (mounted) {
              setState(() {
                _applyDetections(j);
                overlay = boxes.isNotEmpty
                    ? '${boxes.first['klass']} · ${created ? 'FIRST $code' : 'FUSED $code · $sources'}'
                    : (created ? 'FIRST SIGHTING $code — waiting 2nd bus' : 'FUSED $code · $sources buses');
              });
            }
          } catch (_) {
            if (mounted) setState(() => overlay = 'STILL SENT');
          }
          return;
        }
      } catch (_) {}
    }
    try {
      await api('/observations', method: 'POST', body: body);
      if (mounted && !patrol) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Synced observation')));
    } catch (_) {
      await OfflineQueue.enqueue(body);
      if (mounted && !patrol) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Network failed — queued')));
    }
    } finally {
      _busyStill = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final speed = pos == null ? 0.0 : max(0, pos!.speed * 3.6);
    final busLabel = Session.busCode ?? Session.sensorCode;
    return Stack(
      fit: StackFit.expand,
      children: [
        if (cam != null && cam!.value.isInitialized)
          Stack(fit: StackFit.expand, children: [
            CameraPreview(cam!),
            CustomPaint(painter: RddBoxPainter(boxes), child: const SizedBox.expand()),
          ])
        else
          Container(color: Colors.black, alignment: Alignment.center, child: Column(mainAxisSize: MainAxisSize.min, children:[const Icon(Icons.videocam_off, color: Colors.white24, size:36), const SizedBox(height:8), Text(camStatus, style: const TextStyle(color: Colors.white54, fontSize:12)), const SizedBox(height:4), const Text('Mount on windshield for road view', style: TextStyle(color: Colors.white24, fontSize:10))])),
        // HUD overlay — top bar + bottom action
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top HUD
                Container(
                  padding: const EdgeInsets.symmetric(horizontal:12,vertical:10),
                  decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.62), borderRadius: BorderRadius.circular(12), border: Border.all(color: Colors.white.withValues(alpha: 0.12))),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[
                    Row(children:[
                      Container(width:8,height:8,decoration: BoxDecoration(color: cam!=null && cam!.value.isInitialized ? const Color(0xFF0BB98A): Colors.redAccent, shape: BoxShape.circle)),
                      const SizedBox(width:6),
                      Text(overlay, style: const TextStyle(fontSize:11,letterSpacing:.8,fontWeight:FontWeight.w800,color: Colors.white)),
                      const Spacer(),
                      Container(padding: const EdgeInsets.symmetric(horizontal:8,vertical:3), decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(99)), child: Text(busLabel, style: const TextStyle(fontSize:10, fontFamily: 'monospace', color: Colors.white70))),
                    ]),
                    const SizedBox(height:8),
                    Row(children:[
                      _hud('GPS', pos==null? 'UNAVAILABLE': '${pos!.latitude.toStringAsFixed(4)}, ${pos!.longitude.toStringAsFixed(4)}'),
                      const SizedBox(width:12),
                      _hud('SPEED', '${speed.toStringAsFixed(0)} km/h'),
                      const SizedBox(width:12),
                      _hud('IMU', ax?.toStringAsFixed(1) ?? '—'),
                      const SizedBox(width:12),
                      _hud('CAM', camStatus.replaceAll('CAMERA ','')),
                    ]),
                  ]),
                ),
                const Spacer(),
                // Bottom actions — thumb-reachable
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.68), borderRadius: BorderRadius.circular(16), border: Border.all(color: Colors.white.withValues(alpha: 0.10))),
                  child: Column(children:[
                    Row(children:[
                      Expanded(child: Tooltip(message: 'Detect pothole and emit observation', child: FilledButton.icon(onPressed: ()=>_emit(), icon: const Icon(Icons.warning_amber, size:18), label: const Text('DETECT / EMIT POTHOLE'), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0BB98A), padding: const EdgeInsets.symmetric(vertical:14))))),
                    ]),
                    const SizedBox(height:8),
                    Row(children:[
                      Expanded(child: Tooltip(message: 'Queue observation offline', child: OutlinedButton.icon(onPressed: ()=>_emit(forceOffline: true), icon: const Icon(Icons.cloud_off, size:16), label: const Text('QUEUE OFFLINE'), style: OutlinedButton.styleFrom(foregroundColor: Colors.white70, side: BorderSide(color: Colors.white.withValues(alpha: 0.25)), padding: const EdgeInsets.symmetric(vertical:12))))),
                      const SizedBox(width:8),
                      Expanded(child: Tooltip(message: 'Refresh GPS location', child: OutlinedButton.icon(onPressed: () async { final p=await Geolocator.getCurrentPosition().catchError((_)=>pos); if(p!=null) setState(()=>pos=p as Position); }, icon: const Icon(Icons.my_location, size:16), label: const Text('REFRESH GPS'), style: OutlinedButton.styleFrom(foregroundColor: Colors.white70, side: BorderSide(color: Colors.white.withValues(alpha: 0.15)))))),
                    ]),
                    const SizedBox(height:6),
                    const Text('IMU/GPS on this tab. Road boxes: Lens = same /field WebView. 2nd bus confirms.', style: TextStyle(fontSize:9,color: Colors.white38), textAlign: TextAlign.center),
                  ]),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _hud(String k, String v) => Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[Text(k, style: const TextStyle(fontSize:9,letterSpacing:.7,fontWeight:FontWeight.w700,color: Colors.white38)), const SizedBox(height:2), Text(v, style: const TextStyle(fontSize:10,fontWeight:FontWeight.w700,color: Colors.white), maxLines:1, overflow: TextOverflow.ellipsis)]));
}

class RddBoxPainter extends CustomPainter {
  RddBoxPainter(this.boxes);
  final List<Map<String, dynamic>> boxes;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..color = const Color(0xFFE85D4C);
    for (final row in boxes) {
      final b = row['bbox'];
      if (b is! List || b.length < 4) continue;
      final rect = Rect.fromLTRB(
        (b[0] as num).toDouble() * size.width,
        (b[1] as num).toDouble() * size.height,
        (b[2] as num).toDouble() * size.width,
        (b[3] as num).toDouble() * size.height,
      );
      canvas.drawRect(rect, paint);
    }
  }

  @override
  bool shouldRepaint(covariant RddBoxPainter oldDelegate) => true;
}

class QrScanPage extends StatefulWidget {
  const QrScanPage({super.key});
  @override
  State<QrScanPage> createState() => _QrScanPageState();
}

class _QrScanPageState extends State<QrScanPage> {
  final manual = TextEditingController(text: 'urbansense://bus/BUS-042');

  @override
  void dispose() {
    manual.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final fallback = !kPhoneSensors;
    return Scaffold(
      appBar: AppBar(title: Text(fallback ? 'Enter QR payload' : 'Scan QR')),
      body: fallback
          ? Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Text('Camera QR is not available on Windows desktop. Paste a payload (same as a printed QR).'),
                  TextField(controller: manual),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: () => Navigator.pop(context, manual.text.trim()),
                    child: const Text('Use payload'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, 'urbansense://asset/ASSET-001'),
                    child: const Text('ASSET-001'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, 'urbansense://work-order/WO-001'),
                    child: const Text('WO-001'),
                  ),
                ],
              ),
            )
          : MobileScanner(
              onDetect: (capture) {
                final v = capture.barcodes.first.rawValue;
                if (v != null) Navigator.pop(context, v);
              },
            ),
    );
  }
}

class InspectorHome extends StatefulWidget {
  const InspectorHome({super.key});
  @override
  State<InspectorHome> createState() => _InspectorHomeState();
}

class _InspectorHomeState extends State<InspectorHome> {
  Map<String, dynamic>? asset;
  Map<String, dynamic>? wo;
  final notes = TextEditingController();
  String? _queuedJointEvidence;
  int _queuedEvidenceCount = 0;

  @override
  void initState() {
    super.initState();
    _loadQueuedEvidence();
  }

  @override
  void dispose() {
    notes.dispose();
    super.dispose();
  }

  Future<void> _loadQueuedEvidence() async {
    try {
      final items = await OfflineQueue.load();
      String? latest;
      var count = 0;
      for (final it in items) {
        if (it['work_order_evidence'] == true && it['evidence_url'] != null) {
          latest = it['evidence_url'] as String;
          count++;
        }
      }
      if (mounted) setState(() {
        _queuedJointEvidence = latest;
        _queuedEvidenceCount = count;
      });
    } catch (_) {}
  }

  Future<void> _scan() async {
    final payload = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const QrScanPage()));
    if (payload == null) return;
    final found = await api('/qr/lookup?payload=${Uri.encodeQueryComponent(payload)}');
    if (found['kind'] == 'asset' && found['found'] == true) {
      asset = await api('/assets/${found['id']}');
      wo = null;
    } else if (found['kind'] == 'work_order' && found['found'] == true) {
      wo = await api('/work-orders/${found['id']}');
      asset = null;
    }
    await _loadQueuedEvidence();
    setState(() {});
  }

  Future<void> _verify(bool ok) async {
    if (wo == null) return;
    await api('/work-orders/${wo!['id']}/verify', method: 'POST', body: {'passed': ok, 'notes': notes.text});
    wo = await api('/work-orders/${wo!['id']}');
    setState(() {});
  }

  Future<void> _repair() async {
    if (wo == null) return;
    // Prefer queued joint photo evidence_url from bridge SHM (offline queue intact)
    String? evidenceUrl = _queuedJointEvidence;
    if (evidenceUrl == null) {
      try {
        final items = await OfflineQueue.load();
        for (final it in items.reversed) {
          if (it['work_order_evidence'] == true && it['evidence_url'] != null) {
            evidenceUrl = it['evidence_url'] as String;
            break;
          }
        }
      } catch (_) {}
    }
    // enrich evidenceUrl with GPS exif if queued item had extra lat/lon but URL missing (parsing)
    try {
      Position? repairPos;
      try { repairPos = await Geolocator.getCurrentPosition(desiredAccuracy: LocationAccuracy.high, timeLimit: const Duration(seconds: 3)); } catch (_) {}
      if (evidenceUrl != null && !evidenceUrl.contains('lat=') && repairPos != null) {
        final sep = evidenceUrl.contains('?') ? '&' : '?';
        evidenceUrl = '$evidenceUrl${sep}lat=${repairPos.latitude.toStringAsFixed(6)}&lon=${repairPos.longitude.toStringAsFixed(6)}&t=${Uri.encodeComponent(DateTime.now().toUtc().toIso8601String())}&acc=${repairPos.accuracy?.toStringAsFixed(1) ?? "n/a"}';
      }
      final enrichedNotes = (evidenceUrl != null && evidenceUrl.contains('lat='))
          ? '${notes.text} [GPS ${evidenceUrl.split('lat=').last.split('&').first},${evidenceUrl.split('lon=').last.split('&').first} @ ${DateTime.now().toUtc().toIso8601String()}]'
          : notes.text;
      await api('/work-orders/${wo!['id']}/repair', method: 'POST', body: {'notes': enrichedNotes, 'evidence_url': evidenceUrl});
      wo = await api('/work-orders/${wo!['id']}');
      setState(() {});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(evidenceUrl != null ? 'Repair submitted with joint photo $evidenceUrl' : 'Repair submitted')));
      await _loadQueuedEvidence();
    } catch (e) {
      // offline — queue with WO id intact (keeps OfflineQueue queue) — include explicit GPS extra lat/lon
      Position? offPos;
      try { offPos = await Geolocator.getCurrentPosition(timeLimit: const Duration(seconds: 2)); } catch (_) {}
      var offUrl = evidenceUrl ?? 'file://placeholder_joint_${DateTime.now().millisecondsSinceEpoch}.jpg';
      if (!offUrl.contains('lat=') && offPos != null) {
        final sep = offUrl.contains('?') ? '&' : '?';
        offUrl = '$offUrl${sep}lat=${offPos.latitude}&lon=${offPos.longitude}&t=${Uri.encodeComponent(DateTime.now().toUtc().toIso8601String())}';
      }
      await OfflineQueue.enqueue({
        'work_order_evidence': true,
        'work_order_id': wo!['id'],
        'evidence_url': offUrl,
        'local_path': offUrl.replaceAll(RegExp(r'^file://'), '').split('?').first,
        'latitude': offPos?.latitude,
        'longitude': offPos?.longitude,
        'gps_accuracy': offPos?.accuracy,
        'bridge_code': wo!['asset_id'] ?? wo!['public_code'],
        'timestamp': DateTime.now().toUtc().toIso8601String(),
        'source_id': Session.sensorCode,
        'notes': notes.text,
        'extra': {
          'lat': offPos?.latitude,
          'lon': offPos?.longitude,
          'gps_accuracy': offPos?.accuracy,
          'timestamp': DateTime.now().toUtc().toIso8601String(),
          'exif_gps': offPos != null,
        },
      });
      await _loadQueuedEvidence();
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Offline — repair evidence queued (evidence_url + GPS exif)')));
    }
  }

  Future<void> _manual() async {
    Position? pos;
    try {
      pos = await Geolocator.getCurrentPosition();
    } catch (_) {}
    await api('/observations', method: 'POST', body: {
      'event_type': 'ROAD_DAMAGE',
      'severity': 'MEDIUM',
      'latitude': pos?.latitude ?? 28.6139,
      'longitude': pos?.longitude ?? 77.2090,
      'gps_accuracy': pos?.accuracy,
      'source_type': 'INSPECTOR',
      'source_id': 'INSPECTOR',
      'confidence': 0.95,
      'simulated': pos == null,
      'extra': {'notes': notes.text},
    });
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Manual event submitted')));
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('INSPECTOR MODE', style: TextStyle(fontSize: 22)),
          FilledButton(onPressed: _scan, child: const Text('SCAN QR')),
          TextField(controller: notes, decoration: const InputDecoration(labelText: 'Notes / voice-to-text placeholder', helperText: 'Voice-to-text: use keyboard mic')),
          if (_queuedJointEvidence != null) ...[
            const SizedBox(height:8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF0BB98A).withValues(alpha: 0.35))),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children:[
                Row(children:[const Icon(Icons.camera_alt, size:12, color: Color(0xFF0BB98A)), const SizedBox(width:6), const Text('JOINT PHOTO QUEUED', style: TextStyle(fontSize:10, fontWeight: FontWeight.w800, color: Color(0xFF0BB98A)) ), const Spacer(), Text('$_queuedEvidenceCount pending', style: const TextStyle(fontSize:10, color: Colors.white54))]),
                const SizedBox(height:4),
                Text(_queuedJointEvidence!, style: const TextStyle(fontSize:10, fontFamily: 'monospace', color: Colors.white60), maxLines:2, overflow: TextOverflow.ellipsis),
                const Text('Will be sent as evidence_url for Work Order (offline queue intact)', style: TextStyle(fontSize:9, color: Colors.white38)),
                const Text('EXIF GPS: lat/lon/time in URL ?lat=&lon=&t= + extra', style: TextStyle(fontSize:9, color: Colors.white54, fontFamily: 'monospace')),
              ]),
            ),
          ],
          const SizedBox(height:8),
          FilledButton(onPressed: _manual, child: const Text('CREATE MANUAL EVENT')),
          if (asset != null) ...[
            Text('Asset ${asset!['code']} ${asset!['asset_type']}'),
            Text('Condition ${asset!['condition']}'),
          ],
          if (wo != null) ...[
            Row(children: [
              Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: wo!['status'] == 'RESOLVED' ? Colors.green : wo!['status'] == 'FAILED' ? Colors.red : Colors.amber)),
              const SizedBox(width: 6),
              Expanded(child: Text('WO ${wo!['public_code']} ${wo!['status']}')),
            ]),
            Text('${wo!['title']}'),
            FilledButton(onPressed: _repair, child: const Text('SUBMIT REPAIR EVIDENCE')),
            OutlinedButton(onPressed: () => _verify(true), child: const Text('VERIFY REPAIR')),
            OutlinedButton(onPressed: () => _verify(false), child: const Text('FAIL / REOPEN')),
          ],
        ],
      ),
    );
  }
}

class EventsList extends StatefulWidget {
  const EventsList({super.key});
  @override
  State<EventsList> createState() => _EventsListState();
}

class _EventsListState extends State<EventsList> {
  List<dynamic> rows = [];
  String? err;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      rows = await apiList('/events?limit=50');
      err = null;
    } catch (e) {
      err = e.toString();
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          children: [
            if (err != null) ListTile(title: Text(err!, style: const TextStyle(color: Colors.redAccent))),
            ...rows.map((e) => ListTile(
                  title: Text('${e['public_code']} ${e['event_type']}'),
                  subtitle: Text.rich(TextSpan(children: [
                    TextSpan(text: e['simulated'] == true ? 'SIM ' : 'REAL ', style: const TextStyle(fontWeight: FontWeight.bold)),
                    TextSpan(text: '${e['status']}  obs ${e['observation_count']}  ${(e['confidence'] * 100).toStringAsFixed(0)}%'),
                  ])),
                  trailing: Icon(e['status'] == 'RESOLVED' ? Icons.check_circle : Icons.pending),
                )),
          ],
        ),
      ),
    );
  }
}
