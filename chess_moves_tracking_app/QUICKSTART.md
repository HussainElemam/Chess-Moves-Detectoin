# Quick Start Guide

## What Was Implemented

Your Flutter app now has complete camera integration with native chess board detection:

### Live Camera Feed
- ✅ Continuous camera stream from device
- ✅ High resolution capture for accurate piece detection
- ✅ Full-screen preview with overlay

### Real-time Chess Detection
- ✅ Every 3rd frame sent to Kotlin native code
- ✅ Board quad detection using computer vision
- ✅ Perspective correction to top-down view
- ✅ 64 individual squares classified via TensorFlow Lite
- ✅ Stability filtering (requires 2 consecutive identical detections)

### User Interface
- ✅ Live camera preview fills entire screen
- ✅ Dark overlay at bottom shows:
  - Detection status
  - Current board position in FEN notation
  - Auto-updates when new position detected

## How It Works

1. **Camera starts**: User sees live feed from device camera
2. **Frame capture**: Every 3rd frame is extracted from camera stream
3. **Kotlin processing**: Frame sent to native BoardEngine via MethodChannel
4. **Detection pipeline**:
   - Convert YUV420 → BGR color space
   - Downscale if needed (max 960px)
   - Find chess board quad using edge detection
   - Warp board to top-down 640×640 view
   - Normalize color (ensure top-left is dark)
   - Classify each of 64 squares with TensorFlow Lite
   - Generate FEN notation
   - Check stability (only report if consistent)
5. **UI update**: FEN string displayed on overlay when position detected

## File Changes

### Modified
- `lib/main.dart`: Complete rewrite with camera integration

### No Changes Needed
- `android/app/src/main/kotlin/com/example/chess_moves_tracking/MainActivity.kt`: Already correct ✅
- `android/app/src/main/kotlin/com/example/chess_moves_tracking/BoardEngine.kt`: Already correct ✅
- `android/app/src/main/AndroidManifest.xml`: Has camera permission ✅
- `pubspec.yaml`: Has camera package ✅

## Before Running

Make sure you have these files in `android/app/src/main/assets/`:
- `pieces_int8.tflite` - Your trained TensorFlow Lite model
- `label_map.txt` - Label mapping (13 labels: ., P, N, B, R, Q, K, p, n, b, r, q, k)

## Run the App

```bash
cd /home/hussain/Coding/projects/chess_moves_tracking_app
flutter pub get
flutter run
```

## Expected Behavior

1. App launches and says "Initializing..."
2. After ~2 seconds: "Camera initialized"
3. Shows live camera feed
4. Dark overlay at bottom shows "Not detected yet"
5. Point camera at chess board
6. Once board detected and stable: FEN appears in overlay
7. FEN updates whenever pieces move

## Key Parameters (if you want to adjust)

In `lib/main.dart` → `_processImage()`:
- `'processEvery': 3` - Process every Nth frame (higher = less CPU, slower response)

In `android/app/src/main/kotlin/.../BoardEngine.kt` constructor:
- `minStableFrames: Int = 2` - Frames to confirm position (higher = more stable, slower)
- `downscaleMax: Int = 960` - Max pixel dimension (lower = faster, less accurate)
- `insetFrac: Double = 0.08` - Inset from square edges (for classification)

## Data Format

### Input (Dart → Kotlin)
Raw YUV420 camera frame with metadata:
- width, height: Frame dimensions
- bytesY, bytesU, bytesV: Color plane data
- stride/pixelStride: Byte arrangement info
- processEvery: Frame skip rate

### Output (Kotlin → Dart)
FEN string when stable position detected:
```
"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
```
Or `null` if no stable detection yet.

## Debugging

### Check camera permissions
The app requires camera permission. The camera package handles runtime permission requests automatically.

### Check model files
Verify `android/app/src/main/assets/` contains:
```
android/
└── app/
    └── src/
        └── main/
            └── assets/
                ├── pieces_int8.tflite
                └── label_map.txt
```

### Monitor detection
- Check Flutter console for `debugPrint()` output
- Look for "Detected FEN: ..." lines showing recognized positions
- If status says "Error", check the error message in overlay

### Performance
- If laggy, increase `processEvery` (fewer frames to process)
- If not detecting, decrease `processEvery` (more frames to try)
- If flickering, increase `minStableFrames` (more stable but slower)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter App (Dart)                    │
│  CameraController → Live Preview + FEN Display Overlay  │
└────────────────────────────┬────────────────────────────┘
                             │
                    MethodChannel Bridge
                  (vision_bridge - inferFenFromYUV420)
                             │
┌────────────────────────────▼────────────────────────────┐
│              Native Layer (Kotlin/Android)              │
│  ┌──────────────────────────────────────────────────┐   │
│  │ MainActivity                                      │   │
│  │ - Receives YUV420 frame via method channel      │   │
│  │ - Executes on background thread                  │   │
│  │ - Returns FEN or null                            │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │ BoardEngine                                       │   │
│  │ - YUV420 → BGR conversion (OpenCV)              │   │
│  │ - Image scaling & board detection                │   │
│  │ - Perspective warp & normalization               │   │
│  │ - 64 square classification (TFLite)              │   │
│  │ - Stability filtering                            │   │
│  │ - FEN generation                                 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Next Steps

1. Ensure your TensorFlow Lite model and labels are in assets
2. Run the app and test with a physical chess board
3. Adjust parameters based on your board style/lighting
4. Consider adding move validation or game state tracking
