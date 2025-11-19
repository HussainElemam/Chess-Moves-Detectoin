# Chess Moves Tracking App - Implementation Guide

## Overview
This document describes the implementation of the chess board tracking system that captures a live camera feed, processes frames through native Kotlin code for chess piece detection, and displays the detected position in FEN (Forsyth-Edwards Notation) format.

## Architecture

### Components

1. **Flutter UI (Dart)**
   - `lib/main.dart`: Camera preview and FEN display interface
   
2. **Native Layer (Kotlin)**
   - `MainActivity.kt`: Handles method channel communication
   - `BoardEngine.kt`: Computer vision and piece detection using TensorFlow Lite

3. **Platform Bridge**
   - Method Channel named `vision_bridge` for Flutter↔Native communication

## Implementation Details

### 1. Flutter Layer (`lib/main.dart`)

#### Initialization
- **`main()`**: Asynchronously initializes the camera list before running the app
  - `WidgetsFlutterBinding.ensureInitialized()`: Sets up Flutter bindings
  - `availableCameras()`: Queries available cameras on the device

#### ChessBoardTracker Widget
A stateful widget that manages:
- **Camera Controller**: Handles camera initialization and frame streaming
- **State Variables**:
  - `_currentFen`: Displays the detected board position
  - `_status`: Shows current processing status
  - `_isInitialized`: Tracks camera initialization state

#### Camera Initialization (`_initializeCamera()`)
```dart
_cameraController = CameraController(
  cameras.first,
  ResolutionPreset.high,
  enableAudio: false,
);
await _cameraController.initialize();
await _cameraController.startImageStream(_processImage);
```
- Sets resolution to high for better piece detection
- Starts streaming frames to `_processImage()` callback

#### Frame Processing (`_processImage()`)
For each camera frame:
1. Extracts YUV420 plane data (Y, U, V channels)
2. Calls native method `inferFenFromYUV420` via MethodChannel
3. Receives FEN string if a stable chess position is detected
4. Updates UI with the detected position

**Key Parameters**:
- `processEvery: 3`: Processes every 3rd frame (reduces CPU load)
- YUV420 format data extracted directly from camera planes
- Byte strides and pixel strides passed for proper data interpretation

#### UI Layout
- **Camera Preview**: Full-screen live feed from camera
- **Overlay Panel**: Bottom dark overlay showing:
  - Current detection status
  - Detected FEN notation
  - Updates in real-time

### 2. Native Layer (Kotlin)

#### MainActivity.kt
Sets up the method channel handler:
```kotlin
MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "vision_bridge")
    .setMethodCallHandler { call, result ->
        when (call.method) {
            "inferFenFromYUV420" -> {
                // Extract arguments from Flutter
                // Run on background thread to avoid blocking UI
                bg.execute {
                    val fenOrNull = engineVision.processYuvAndGetFen(...)
                    runOnUiThread { result.success(fenOrNull) }
                }
            }
        }
    }
```

**Features**:
- Offloads heavy computation to background thread
- Returns null if no stable change detected
- Returns FEN string when position is confirmed

#### BoardEngine.kt
Performs the actual chess board detection and piece recognition:

**Key Processes**:

1. **YUV420 → BGR Conversion** (`yuv420ToNV21()` → OpenCV color conversion)
   - Converts camera YUV420 format to BGR for OpenCV processing

2. **Image Scaling** (`resizeMax()`)
   - Downscales large images (max 960px) for faster processing
   - Maintains aspect ratio

3. **Board Detection** (`detectQuad()`)
   - Edge detection with Canny edge detector
   - Binary thresholding and morphological operations
   - Contour detection to find chess board quad
   - Scores quads based on:
     - Size relative to image
     - Aspect ratio (prefers square shapes)
     - Internal contrast (line prominence)

4. **Board Perspective Correction** (`warpFromQuad()`)
   - Applies perspective transform to create top-down view
   - Output: 640×640 warped board image

5. **Color Normalization** (`ensureTopLeftDark()`)
   - Ensures consistent board orientation
   - Flips board if top-left square is light instead of dark

6. **Piece Classification** (`classify64()`)
   - Processes each of 64 squares individually
   - Extracts and resizes square to model input size
   - Handles both FLOAT32 and INT8 quantized models
   - Uses TensorFlow Lite for piece classification
   - Returns 64 piece labels (one per square)

7. **Stability Filtering**
   - Tracks frame count with `frameCount` and `processEvery`
   - Maintains candidate position with `minStableFrames`
   - Only outputs FEN when position is stable (confirmed multiple frames)

8. **FEN Generation** (`toFen()`)
   - Converts 64 piece labels to FEN notation
   - Compresses consecutive empty squares into numbers
   - Returns standard FEN format: `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1`

### 3. Data Flow

```
Camera Frame (YUV420)
    ↓
[Flutter] _processImage()
    ↓
[MethodChannel] inferFenFromYUV420
    ↓
[Kotlin] MainActivity - Background thread
    ↓
[Kotlin] BoardEngine.processYuvAndGetFen()
    ├─ YUV420 → BGR conversion
    ├─ Image scaling
    ├─ Board quad detection
    ├─ Perspective correction
    ├─ Color normalization
    ├─ 64-square piece classification
    ├─ Stability checking
    └─ FEN generation
    ↓
[MethodChannel] Result: FEN string or null
    ↓
[Flutter] Update UI with detected position
```

## Performance Optimizations

1. **Frame Skipping**: Process every 3rd frame (`processEvery: 3`)
2. **Image Downscaling**: Max 960px dimension before processing
3. **Background Threading**: Heavy computation off main thread
4. **INT8 Quantization**: Uses int8 TensorFlow Lite model for speed
5. **Stability Filtering**: Avoids flickering false detections

## Model Requirements

The app expects the following assets in `android/app/src/main/assets/`:
- `pieces_int8.tflite`: TensorFlow Lite model (INT8 quantized) for piece classification
- `label_map.txt`: Label mapping file with 13 labels:
  ```
  .
  P
  N
  B
  R
  Q
  K
  p
  n
  b
  r
  q
  k
  ```

## Configuration Parameters

In `BoardEngine.kt` constructor:
- `warpSize`: Warped board dimension (640px)
- `insetFrac`: Inset fraction for square extraction (0.08 = 8%)
- `tileSize`: Tile size for processing (96px) - not used in current version
- `minStableFrames`: Frames needed for position stability (2)
- `downscaleMax`: Maximum dimension before scaling (960px)

## Permissions

**Required in `AndroidManifest.xml`**:
```xml
<uses-permission android:name="android.permission.CAMERA"/>
```

The app requests camera permission from Flutter's camera package.

## Testing & Debugging

### Build and Run
```bash
flutter pub get
flutter run
```

### Expected Output
- App shows live camera feed with dark overlay at bottom
- Overlay displays:
  - Status: "Camera initialized", "Position detected", or error messages
  - FEN: Chess position in standard notation
  - Updates as stable positions are detected

### Debug Logging
- Flutter: Logs in `_processImage()` show detected FEN strings
- Kotlin: Logs show frame processing details (if enabled)

## Troubleshooting

### Camera not initializing
- Check that camera permission is granted
- Ensure device has a camera
- Check logcat for initialization errors

### No pieces detected
- Verify lighting conditions (good illumination important)
- Check that chess board is fully visible and approximately square
- Ensure TensorFlow Lite model and labels are in assets folder
- Verify board is right-side up (top-left should be dark square)

### Slow performance
- Frame processing is on background thread; UI should remain responsive
- Adjust `processEvery` value to process fewer frames per second
- Reduce `downscaleMax` for lower resolution processing

### Wrong piece detection
- Check that model was trained on similar board imagery
- Ensure label_map.txt matches model's label order
- Verify INT8 quantization scale/zeroPoint in model are correct

## Future Enhancements

1. Add move history tracking
2. Implement chessmove validation against rules
3. Add configurable sensitivity/stability thresholds
4. Support for different board sizes/styles
5. Audio feedback for detected positions
6. Export detected moves in PGN format
