import 'dart:convert';
import 'package:camera/camera.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

const _channel = MethodChannel('vision_bridge');

Future<void> onFrame(CameraImage img) async {
  if (img.format.group != ImageFormatGroup.yuv420) return;
  final res = await _channel.invokeMethod<String>('inferFenFromYUV420', {
    'width': img.width,
    'height': img.height,
    'bytesY': img.planes[0].bytes,
    'bytesU': img.planes[1].bytes,
    'bytesV': img.planes[2].bytes,
    'strideY': img.planes[0].bytesPerRow,
    'strideU': img.planes[1].bytesPerRow,
    'strideV': img.planes[2].bytesPerRow,
    'pixelStrideU': img.planes[1].bytesPerPixel,
    'pixelStrideV': img.planes[2].bytesPerPixel,
    'processEvery': 3, // process every 3rd frame
  });
  if (res == null) return; // no stable change yet
  await http.post(
    Uri.parse('https://YOUR_BACKEND/ingest'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'fen': res, 'ts': DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000}),
  );
}
