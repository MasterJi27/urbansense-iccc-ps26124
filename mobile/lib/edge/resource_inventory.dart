import 'dart:io';
import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:camera/camera.dart';

/// Headless probe — no BuildContext, no GUI.
/// Returns what THIS phone can actually do for PS26124.
class ResourceInventory {
  bool accelOk = false;
  bool gyroOk = false;
  bool magOk = false;
  bool gpsOk = false;
  bool cameraOk = false;
  int? batteryPct;
  String net = 'UNKNOWN';
  bool lowRam = false; // heuristic: <3GB via total physical? fallback battery+model
  String mode = 'CAPTURE_AND_SENSOR'; // HIGH=EDGE_AI MEDIUM=LIGHTWEIGHT LOW=CAPTURE

  Future<ResourceInventory> probe() async {
    // IMU — try each stream with 1s timeout, no UI
    if (!Platform.isWindows && !Platform.isLinux && !Platform.isMacOS) {
      try {
        final sub = accelerometerEventStream().listen((_) {});
        await Future.delayed(const Duration(milliseconds: 300));
        await sub.cancel();
        accelOk = true;
      } catch (_) { accelOk = false; }
      try {
        final sub = gyroscopeEventStream().listen((_) {});
        await Future.delayed(const Duration(milliseconds: 300));
        await sub.cancel();
        gyroOk = true;
      } catch (_) { gyroOk = false; }
      try {
        final sub = magnetometerEventStream().listen((_) {});
        await Future.delayed(const Duration(milliseconds: 300));
        await sub.cancel();
        magOk = true;
      } catch (_) { magOk = false; }
    }
    try {
      final svc = await Geolocator.isLocationServiceEnabled();
      gpsOk = svc;
    } catch (_) { gpsOk = false; }
    try {
      final cams = await availableCameras();
      cameraOk = cams.isNotEmpty;
    } catch (_) { cameraOk = false; }
    try {
      batteryPct = await Battery().batteryLevel;
    } catch (_) {}
    try {
      final c = await Connectivity().checkConnectivity();
      net = c.map((e) => e.name).join(',');
    } catch (_) { net = 'UNAVAILABLE'; }
    // mode decision — phone-only, no server needed
    if ((batteryPct ?? 100) < 25) {
      mode = 'CAPTURE_AND_SENSOR';
    } else if (!cameraOk) {
      mode = 'CAPTURE_AND_SENSOR';
    } else if ((batteryPct ?? 100) < 60) {
      mode = 'LIGHTWEIGHT_EDGE_AI';
    } else {
      mode = 'LIGHTWEIGHT_EDGE_AI'; // never full EDGE_AI on phone alone
    }
    return this;
  }

  Map<String, dynamic> toHeartbeatBase() => {
    'imu_accel': accelOk ? 'ONLINE' : 'UNAVAILABLE',
    'imu_gyro': gyroOk ? 'ONLINE' : 'UNAVAILABLE',
    'imu_mag': magOk ? 'ONLINE' : 'UNAVAILABLE',
    'gps': gpsOk ? 'ONLINE' : 'UNAVAILABLE',
    'camera': cameraOk ? 'ONLINE' : 'OFFLINE',
    'battery_pct': batteryPct,
    'network': net,
    'mode': mode,
  };
}
