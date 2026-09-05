import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

const _apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://app-urbansense-yngmbk.azurewebsites.net',
);

/// Same on-device /field engine as Safari/Chrome. Not a second detector.
class FieldWebLens extends StatefulWidget {
  const FieldWebLens({super.key});

  @override
  State<FieldWebLens> createState() => _FieldWebLensState();
}

class _FieldWebLensState extends State<FieldWebLens> {
  WebViewController? _controller;
  String? _err;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_boot());
  }

  Future<void> _boot() async {
    try {
      if (!Platform.isWindows && !Platform.isLinux && !Platform.isMacOS) {
        try {
          await availableCameras();
        } catch (_) {}
      }
      final controller = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setBackgroundColor(const Color(0xFF070B12))
        ..setNavigationDelegate(
          NavigationDelegate(
            onPageFinished: (_) {
              if (mounted) setState(() => _loading = false);
            },
            onWebResourceError: (error) {
              if (mounted) {
                setState(() {
                  _loading = false;
                  _err = error.description;
                });
              }
            },
          ),
        )
        ..loadRequest(Uri.parse('$_apiBase/field'));
      final platform = controller.platform;
      if (platform is AndroidWebViewController) {
        await platform.setMediaPlaybackRequiresUserGesture(false);
        platform.setOnPlatformPermissionRequest((request) {
          request.grant();
        });
      }
      if (mounted) {
        setState(() {
          _controller = controller;
          _err = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _err = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ROAD LENS'),
        backgroundColor: const Color(0xFF070B12),
      ),
      body: Column(
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(12, 8, 12, 8),
            child: Text(
              'Same /field page as the jury phone. Boxes are on-device WASM. Azure still is the official event. Not a child detector. Not Azure GPU.',
              style: TextStyle(fontSize: 12, color: Colors.white54),
            ),
          ),
          if (_err != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                'WebView failed. Open $_apiBase/field in Chrome. $_err',
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              ),
            ),
          Expanded(
            child: _controller == null
                ? Center(
                    child: _loading
                        ? const CircularProgressIndicator()
                        : const Text('Lens not ready', style: TextStyle(color: Colors.white54)),
                  )
                : Stack(
                    children: [
                      WebViewWidget(controller: _controller!),
                      if (_loading)
                        const Align(
                          alignment: Alignment.topCenter,
                          child: LinearProgressIndicator(),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
