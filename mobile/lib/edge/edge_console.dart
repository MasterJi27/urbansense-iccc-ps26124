import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'edge_service.dart';

/// EdgeConsole v3 — driver-friendly but still LIGHTWEIGHT.
/// No CameraPreview, no map, no heavy animation. Just status grid + big action + color log.
/// 2GB phone safe: const widgets, single ListView, max 80 logs.
class EdgeConsole extends StatefulWidget {
  const EdgeConsole({super.key});
  @override
  State<EdgeConsole> createState() => _EdgeConsoleState();
}

class _EdgeConsoleState extends State<EdgeConsole> {
  final List<String> _logs = [];
  bool _busy = false;
  bool _syncing = false;
  bool _useHindi = false;
  static const _titleEn = 'EDGE — phone only, no GUI load';
  static const _titleHi = 'EDGE — सिर्फ फोन, हल्का UI';
  static const _subEn = 'PS26124 phone-only • ~1KB JSON • no video';
  static const _subHi = 'PS26124 सिर्फ फोन • ~1KB JSON • वीडियो नहीं';
  String _filter = 'all';
  Timer? _tick;
  DateTime? _startedAt;
  DateTime? _lastSyncAt;
  String _elapsed = '00:00';

  @override
  void initState() {
    super.initState();
    _restoreHindi();
    EdgeService.I.onLog = (line) {
      if (!mounted) return;
      setState(() {
        _logs.insert(0, line);
        if (_logs.length > 80) _logs.removeLast();
        if (line.toLowerCase().contains('sync done')) {
          _lastSyncAt = DateTime.now();
        }
      });
    };
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _restoreHindi() async {
    try {
      final p = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() => _useHindi = p.getBool('use_hindi') ?? false);
    } catch (_) {}
  }

  Future<void> _saveHindi(bool v) async {
    setState(() => _useHindi = v);
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool('use_hindi', v);
    } catch (_) {}
  }

  void _startElapsed() {
    _startedAt = DateTime.now();
    _elapsed = '00:00';
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted || _startedAt == null) return;
      final s = DateTime.now().difference(_startedAt!).inSeconds;
      setState(() {
        _elapsed =
            '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toString().padLeft(2, '0')}';
      });
    });
  }

  void _stopElapsed() {
    _tick?.cancel();
    _tick = null;
    _startedAt = null;
  }

  Future<void> _toggle() async {
    setState(() => _busy = true);
    try {
      if (EdgeService.I.running) {
        await EdgeService.I.stop();
        _stopElapsed();
      } else {
        await EdgeService.I.start();
        _startElapsed();
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _syncNow() async {
    setState(() => _syncing = true);
    try {
      await EdgeService.I.syncNow();
    } finally {
      if (mounted) {
        setState(() {
          _syncing = false;
          _lastSyncAt = DateTime.now();
        });
      }
    }
  }

  Color _logColor(String line) {
    final l = line.toLowerCase();
    if (l.contains('ok') || l.contains('done') || l.contains('bridge brg')) {
      return const Color(0xFF0BB98A);
    }
    if (l.contains('queued') || l.contains('offline') || l.contains('pending')) {
      return Colors.amber;
    }
    if (l.contains('error') || l.contains('fail') || l.contains('exception')) {
      return Colors.redAccent;
    }
    return Colors.white60;
  }

  bool _matchFilter(String line) {
    if (_filter == 'all') return true;
    final l = line.toLowerCase();
    if (_filter == 'ok') {
      return l.contains('ok') || l.contains('done') || l.contains('bridge brg');
    }
    if (_filter == 'queued') {
      return l.contains('queued') || l.contains('offline') || l.contains('pending');
    }
    if (_filter == 'error') {
      return l.contains('error') || l.contains('fail') || l.contains('exception');
    }
    return true;
  }

  Widget _tile(String label, String value, bool ok, {bool warn = false}) {
    final dot = !ok
        ? Colors.white24
        : warn
            ? Colors.amber
            : const Color(0xFF0BB98A);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: dot.withValues(alpha: 0.35)),
      ),
      child: Row(children: [
        Container(width: 8, height: 8, decoration: BoxDecoration(color: dot, shape: BoxShape.circle)),
        const SizedBox(width: 8),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: const TextStyle(fontSize: 11, letterSpacing: 0.8, color: Colors.white54, fontWeight: FontWeight.w700)),
            const SizedBox(height: 1),
            Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.white, fontFamily: 'monospace')),
          ]),
        ),
      ]),
    );
  }

  Widget _chip(String key, String label) {
    final sel = _filter == key;
    return Semantics(
      button: true,
      selected: sel,
      label: 'Filter logs: $label',
      child: GestureDetector(
        onTap: () => setState(() => _filter = key),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: sel
                ? const Color(0xFF0BB98A).withValues(alpha: 0.2)
                : Colors.white10,
            borderRadius: BorderRadius.circular(99),
            border: Border.all(
              color: sel
                  ? const Color(0xFF0BB98A).withValues(alpha: 0.6)
                  : Colors.white12,
            ),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: sel ? Colors.white : Colors.white70,
            ),
          ),
        ),
      ),
    );
  }

  String _shortBase(String b) {
    return b.replaceFirst('http://', '').replaceFirst('https://', '');
  }

  String _fmtClock(DateTime? t) {
    if (t == null) return 'never';
    return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:${t.second.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final s = EdgeService.I;
    final running = s.running;
    final speedKmh = s.lastPos == null ? 0.0 : (s.lastPos!.speed * 3.6).clamp(0, 200);
    final gpsTxt = s.lastPos == null ? 'SIM (Delhi)' : '${s.lastPos!.latitude.toStringAsFixed(4)}, ${s.lastPos!.longitude.toStringAsFixed(4)}';
    final batt = s.batteryPct;
    final battWarn = batt != null && batt < 20;
    final visible = _logs.where(_matchFilter).toList();

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            // header — page-contract: crumbs + title 15/800 + sub 11 muted + status role
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
              child: Row(children: [
                Container(
                  width: 10, height: 10,
                  decoration: BoxDecoration(
                    color: running ? const Color(0xFF0BB98A) : Colors.white24,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('EDGE • FIELD CONSOLE', style: TextStyle(fontSize: 11, letterSpacing: 1.0, color: Colors.white38, fontWeight: FontWeight.w700)),
                    Semantics(
                      header: true,
                  child: Text(
                    running
                        ? (_useHindi ? 'EDGE चालू • ${s.busCode ?? "अनबाउंड"}' : 'EDGE RUNNING • ${s.busCode ?? "UNBOUND"}')
                        : (_useHindi ? 'EDGE बंद • ${s.busCode ?? "अनबाउंड"}' : 'EDGE IDLE • ${s.busCode ?? "UNBOUND"}'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, letterSpacing: 0.5),
                      ),
                    ),
                    Semantics(
                      liveRegion: true,
                      label: running ? 'Edge running. ${s.queuedCount} queued.' : 'Edge idle. ${s.queuedCount} queued.',
                      child: Text(
                        _useHindi ? _subHi : _subEn,
                        style: TextStyle(fontSize: 11, color: Colors.white.withValues(alpha: 0.5)),
                      ),
                    ),
                  ]),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(color: Colors.white10, borderRadius: BorderRadius.circular(99)),
                  child: Text('${speedKmh.toStringAsFixed(0)} km/h', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
                ),
              ]),
            ),
            // Hindi toggle — in-memory only, no persistence
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 6, 14, 0),
              child: Row(children: [
                const Text('हिंदी', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white54)),
                Switch(
                  value: _useHindi,
                  activeColor: const Color(0xFF0BB98A),
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                  onChanged: _saveHindi,
                ),
                Expanded(
                  child: Text(
                    _useHindi ? _titleHi : _titleEn,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white54),
                  ),
                ),
              ]),
            ),
            if (running)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Semantics(
                  liveRegion: true,
                  label: 'Running elapsed $_elapsed',
                  child: Text(
                    '● RUNNING $_elapsed',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, fontFamily: 'monospace', color: Color(0xFF0BB98A)),
                  ),
                ),
              ),
            // status grid 2x2 — cheap, no animation
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
              child: GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
                childAspectRatio: 2.4,
                children: [
                  _tile('GPS', gpsTxt, s.gpsOk || s.lastPos != null),
                  _tile('IMU', s.accelOk ? 'rms ${s.lastRms.toStringAsFixed(2)}g' : 'WAITING', s.accelOk),
                  _tile('BATTERY', batt == null ? 'n/a' : '$batt% ${battWarn ? "• saver" : ""}', batt != null, warn: battWarn),
                  _tile('QUEUE', s.queuedCount == 0 ? 'empty' : '${s.queuedCount} pending', true, warn: s.queuedCount > 0),
                ],
              ),
            ),
            // stats
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                child: Text(
                  _useHindi
                      ? 'मोड ${s.processingTier} • ${s.processingMode} • YOLO नहीं • ~1KB JSON\nsent ${s.sentObs} obs • ${s.sentBatches} bridge • net ${s.net}'
                      : 'mode ${s.processingTier} • ${s.processingMode} • no YOLO on phone • ~1KB JSON\nsent ${s.sentObs} obs • ${s.sentBatches} bridge • net ${s.net}',
                  style: const TextStyle(fontSize: 11, fontFamily: 'monospace', color: Colors.white54, height: 1.45),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 8, 14, 0),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                child: Semantics(
                  liveRegion: true,
                  label: 'Last sync ${_fmtClock(_lastSyncAt)}',
                  child: Text(
                    'sync ${_fmtClock(_lastSyncAt)} • ${_shortBase(s.apiBase)} • ${s.busCode ?? "UNBOUND"}  ⧉ tap to copy',
                    style: const TextStyle(fontSize: 11, fontFamily: 'monospace', color: Colors.white54),
                  ),
                ),
              ),
            ),
            // log + chips + mapping — scrollable, fills remaining space
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
                children: [
                  Row(children: [
                    const Expanded(child: Text('LOG — latest first', style: TextStyle(fontSize: 11, color: Colors.white38, letterSpacing: 1, fontWeight: FontWeight.w700))),
                    TextButton(
                      onPressed: visible.isEmpty
                          ? null
                          : () async {
                              await Clipboard.setData(ClipboardData(text: visible.join('\n')));
                              if (!context.mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Log copied')));
                            },
                      style: TextButton.styleFrom(minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap, padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4)),
                      child: const Text('Copy log', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                    ),
                  ]),
                  const SizedBox(height: 6),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(children: [
                      _chip('all', 'All'),
                      const SizedBox(width: 6),
                      _chip('ok', 'ok'),
                      const SizedBox(width: 6),
                      _chip('queued', 'queued'),
                      const SizedBox(width: 6),
                      _chip('error', 'error'),
                    ]),
                  ),
                  const SizedBox(height: 6),
                  Container(
                    height: 280,
                    decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                    child: visible.isEmpty
                        ? const Center(
                            child: Padding(
                              padding: EdgeInsets.all(16),
                              child: Text('START — windshield mount\nIMU+GPS trigger only. No live YOLO. No video upload.', textAlign: TextAlign.center, style: TextStyle(color: Colors.white24, fontSize: 11, height: 1.5)),
                            ),
                          )
                        : ListView.builder(
                            itemCount: visible.length,
                            itemBuilder: (_, i) => Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              child: Text(visible[i], style: TextStyle(fontSize: 11, fontFamily: 'monospace', color: _logColor(visible[i]))),
                            ),
                          ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    decoration: BoxDecoration(color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(10), border: Border.all(color: Colors.white12)),
                    child: const ExpansionTile(
                      title: Text('PS26124 mapping (phone-only)', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: Colors.white)),
                      iconColor: Colors.white54,
                      collapsedIconColor: Colors.white54,
                      childrenPadding: EdgeInsets.fromLTRB(14, 0, 14, 12),
                      children: [
                        Text('• POTHOLE → IMU spike (no gyro turn) + speed 8–70 → ~1KB JSON. Phone RULE_BASED, YOLO on backend still.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• BRIDGE → 90m geofence + samples → POST /bridge/batch. Screening, not collapse prediction.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• SCHOOL → 80m school zone + speed <25 → PEDESTRIAN_RISK. Not a child-detector model.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• CONGESTION → GPS speed <10 dwell → RULE_BASED proxy. Count is backend fusion.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• RASH → GPS >54 km/h. Plate OCR is backend ANPR, never on phone.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• OFFLINE → pending_observations.json (cap 500) survives reboot. SYNC every 15s.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                        Text('• NO YOLO / NO VIDEO / NO FEDERATED LEARNING on this 2GB phone.', style: TextStyle(fontSize: 11, color: Colors.white54, height: 1.5)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text('Windshield mount • JWT secure • offline survives reboot', textAlign: TextAlign.center, style: TextStyle(fontSize: 11, color: Colors.white24)),
                ],
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF0F172A),
            border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.12))),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(children: [
                Expanded(child: Text(s.lowData ? 'Low-data ON • saver' : 'Low-data OFF', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700))),
                Switch(
                  value: s.lowData,
                  activeColor: const Color(0xFF0BB98A),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  onChanged: (v) async {
                    await s.setLowData(v);
                    if (mounted) setState(() {});
                  },
                ),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                  flex: 2,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _toggle,
                    icon: Icon(running ? Icons.stop : Icons.play_arrow, size: 20),
                    label: Text(
                      running
                          ? (_useHindi ? 'रोकें STOP' : 'STOP')
                          : (_useHindi ? 'शुरू START' : 'START'),
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: running ? Colors.redAccent : const Color(0xFF0BB98A),
                      minimumSize: const Size.fromHeight(54),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 1,
                  child: OutlinedButton.icon(
                    onPressed: (_syncing || s.queuedCount == 0) ? null : _syncNow,
                    icon: _syncing
                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.sync, size: 16),
                    label: Text(s.queuedCount > 0 ? 'SYNC (${s.queuedCount})' : 'SYNCED'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white70,
                      side: const BorderSide(color: Colors.white24),
                      minimumSize: const Size.fromHeight(54),
                    ),
                  ),
                ),
              ]),
            ],
          ),
        ),
      ),
    );
  }
}
