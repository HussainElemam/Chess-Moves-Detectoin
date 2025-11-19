# Implementation Details & Troubleshooting Guide

## File Locations & Storage

### Android External Files Directory
```
/data/data/com.example.chess_moves_tracking/files/
```

This directory is:
- **Persistent** - survives app restarts
- **Private to your app** - other apps can't access
- **Backed by Android's scoped storage** - no special permissions needed beyond standard permissions
- **Automatically cleared** when app is uninstalled

### Accessing Files via ADB

```bash
# View all saved files
adb shell ls -la /data/data/com.example.chess_moves_tracking/files/

# Download a specific log file
adb pull /data/data/com.example.chess_moves_tracking/files/chess_logs/game_123_20251118_143045.log

# Download all sample images
adb pull /data/data/com.example.chess_moves_tracking/files/chess_samples/

# Clear sample images (keep logs)
adb shell rm /data/data/com.example.chess_moves_tracking/files/chess_samples/*.png
```

## Code Changes Breakdown

### 1. LogEntry Data Class (Lines 55-63)

**Before:**
```kotlin
data class LogEntry(
    val timestamp: String,
    val frameNumber: Int,
    val gameId: String?,
    val labels64: List<String>,
    val fen: String,
    val candidate: String?,
    val stable: Int,
    val isStableChange: Boolean
)
```

**After:**
```kotlin
data class LogEntry(
    val timestamp: String,
    val frameNumber: Int,
    val gameId: String?,
    val labels64: List<String>,
    val fen: String,
    val candidate: String?,
    val stable: Int,
    val isStableChange: Boolean,
    val imageFile: String? = null  // ← NEW: Path to saved frame image
)
```

### 2. processYuvAndGetFen Method (Lines 113-186)

**Key Change**: Replaced random FEN generation with model inference

**Before** (lines 166-182):
```kotlin
// TEMPORARY: For testing, generate random positions instead of actual detection
val currentTime = System.currentTimeMillis()
val fen = if (currentTime - lastRandomFenTime >= 1000) {
    lastRandomFen = generateRandomFen()
    lastRandomFenTime = currentTime
    lastRandomFen!!
} else {
    lastRandomFen ?: generateRandomFen()
}
val labels64 = fenToLabels64(fen)
// TEMPORARY: Always return new positions (skip stability check)
```

**After** (lines 159-177):
```kotlin
// Actual model detection
val labels64 = classify64(warp)
val fen = toFen(labels64)

// Stability check: only return when stable position is detected
val isStableChange: Boolean
if (prevFen == null) {
    prevFen = fen
    candidate = fen; stable = 1
    isStableChange = true
} else {
    if (candidate == fen) {
        stable++
    } else {
        candidate = fen
        stable = 1
    }
    // Return only when we have a stable change
    isStableChange = if (stable >= minStableFrames && prevFen != candidate) {
        prevFen = candidate
        true
    } else {
        false
    }
}
```

### 3. logPrediction Method (Lines 598-630)

**Enhanced to save frame images:**

```kotlin
private fun logPrediction(
    labels64: List<String>,
    fen: String,
    candidate: String?,
    stable: Int,
    isStableChange: Boolean,
    warpImage: Mat? = null  // ← NEW: Optional warp image parameter
) {
    val timestamp = dateFormat.format(Date())
    
    // Save frame image if provided
    var imageFile: String? = null
    if (warpImage != null) {
        try {
            imageFile = File(sampleDir, "frame_${frameCount}_${System.currentTimeMillis()}.png").absolutePath
            Imgcodecs.imwrite(imageFile, warpImage)  // ← NEW: Save image
        } catch (e: Exception) {
            android.util.Log.w("BoardEngine", "Failed to save frame image: ${e.message}")
        }
    }
    
    val entry = LogEntry(
        timestamp = timestamp,
        frameNumber = frameCount,
        gameId = gameId,
        labels64 = labels64,
        fen = fen,
        candidate = candidate,
        stable = stable,
        isStableChange = isStableChange,
        imageFile = imageFile  // ← NEW: Include image path
    )
    logEntries.add(entry)
}
```

### 4. saveLogs Method (Lines 632-665)

**Enhanced with more metadata:**

```kotlin
fun saveLogs(): String? {
    if (logEntries.isEmpty()) {
        return null
    }

    val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
    val gameIdPart = if (gameId != null) "game_${gameId}_" else "predictions_"
    val logFile = File(logDir, "${gameIdPart}${timestamp}.log")

    try {
        FileWriter(logFile).use { writer ->
            writer.append("Chess Board Detection Log\n")
            writer.append("Game ID: ${gameId ?: "N/A"}\n")
            writer.append("Generated: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())}\n")
            writer.append("Total Entries: ${logEntries.size}\n")
            writer.append("Sample Directory: ${sampleDir.absolutePath}\n")  // ← NEW
            writer.append("=".repeat(100)).append("\n\n")

            logEntries.forEach { entry ->
                // ... existing fields ...
                if (entry.imageFile != null) {  // ← NEW
                    writer.append("Frame Image: ${entry.imageFile}\n")
                }
                writer.append("-".repeat(100)).append("\n")
            }
        }
        android.util.Log.i("BoardEngine", "Logs saved to: ${logFile.absolutePath}")  // ← NEW
        return logFile.absolutePath
    } catch (e: Exception) {
        android.util.Log.e("BoardEngine", "Error saving logs: ${e.message}", e)
        return null
    }
}
```

### 5. Removed Code

These helper functions and variables were removed (no longer needed):

- `lastRandomFenTime` variable
- `lastRandomFen` variable
- `generateRandomFen()` function
- `fenToLabels64()` function

## Stability Algorithm Explained

The app uses a state machine to detect stable board positions:

```
State Diagram:
═════════════════════════════════════════════════════════════════

Initial State:
    prevFen = null
        ↓
First frame prediction arrives
        ↓
    prevFen = fen
    candidate = fen
    stable = 1
    return TRUE (first detection)

Subsequent frames:
        ↓
    New frame prediction: fen₂
        ├─── If fen₂ == candidate
        │       stable++
        │       If stable >= minStableFrames AND candidate != prevFen:
        │           prevFen = candidate
        │           return TRUE (stable change detected)
        │       Else:
        │           return FALSE (not stable yet)
        │
        └─── If fen₂ != candidate
                candidate = fen₂
                stable = 1
                return FALSE (position changed, reset counter)
```

### Example Timeline

```
Frame 1: Detected FEN-A
    → prevFen=null, candidate=A, stable=1 → RETURN (new position)

Frame 2: Detected FEN-A (same as frame 1)
    → candidate=A, stable=2 → (stable >= 2) → RETURN (position confirmed)

Frame 3: Detected FEN-B (new position)
    → candidate=B, stable=1 → (changed, reset counter) → NO RETURN

Frame 4: Detected FEN-B (same as frame 3)
    → candidate=B, stable=2 → (stable >= 2 AND B != A) → RETURN (new move detected)

Frame 5: Detected FEN-B (still same)
    → candidate=B, stable=3 → (no change) → NO RETURN (already confirmed)

Frame 6: Detected FEN-C (another new position)
    → candidate=C, stable=1 → (changed, reset) → NO RETURN
```

## Performance Metrics

### Memory Usage
- **Model**: ~2-5 MB (INT8 quantized)
- **Input buffer**: ~2 MB (512×512 RGB)
- **Per-frame overhead**: ~5 MB peak

### Processing Time (per frame)
- Frame reception: < 1ms
- YUV → BGR conversion: 2-3ms
- Board detection: 5-10ms
- Perspective warp: 2-3ms
- Model inference (64 squares): 10-20ms
- **Total**: ~20-40ms per processed frame

### Frame Rate
- Processes every 3rd frame by default (reduces processing load)
- With ~30 fps input: ~10 fps inference rate
- Adjustable via `processEvery` parameter

## Debugging Tips

### Check if Model is Loaded
```kotlin
// Add this to onCreate() if you want explicit verification
try {
    val fd = ctx.assets.openFd("pieces_int8.tflite")
    Log.i("BoardEngine", "Model file found: ${fd.declaredLength} bytes")
} catch (e: Exception) {
    Log.e("BoardEngine", "Model file not found!")
}
```

### Enable Verbose Logging
Add to `MainActivity.kt`:
```kotlin
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    if (BuildConfig.DEBUG) {
        android.util.Log.setLogLevel(Log.VERBOSE)
    }
}
```

### Monitor Frame Processing
Check logcat for "BoardEngine" tags:
```bash
adb logcat | grep BoardEngine
```

### Verify Image Saving
Check if images are being created:
```bash
# Watch for new files
adb shell ls -la /data/data/com.example.chess_moves_tracking/files/chess_samples/ | tail -20
```

## Configuration Tuning

### Adjust Stability Threshold
In `BoardEngine.kt` init section, change:
```kotlin
private val minStableFrames: Int = 2,  // Default: 2
// Change to 3 for more stability, 1 for faster response
```

### Adjust Processing Frequency
In `MainActivity.kt`, change:
```kotlin
val processEvery = call.argument<Int>("processEvery") ?: 3  // Default: 3
// Change to 1 for every frame (slower), 5 for every 5th frame (faster)
```

### Adjust Board Detection Sensitivity
In `detectQuad()` method, change contour area threshold:
```kotlin
val minArea = 0.05 * imgArea  // Default: 5% of image
// Decrease for smaller boards, increase for noise-free images
```

### Adjust Color Space Conversion
The code uses `COLOR_YUV2BGR_NV21` which is standard. To debug:
```kotlin
// Temporarily save the converted BGR image
val bgrFile = File(sampleDir, "bgr_${frameCount}.png")
Imgcodecs.imwrite(bgrFile.absolutePath, bgr)
```

## Storage Management

### Estimated Disk Usage
- **Logs**: ~5-10 KB per entry (with FEN + metadata)
- **Frame images**: ~100-200 KB per PNG
- **For 1 hour of recording**: ~5-10 MB logs + 100-200 MB images

### Cleanup Strategy
```bash
# Keep logs, delete images
adb shell rm -r /data/data/com.example.chess_moves_tracking/files/chess_samples/*

# Keep only recent logs
adb shell find /data/data/com.example.chess_moves_tracking/files/chess_logs/ \
  -type f -mtime +7 -delete
```

## Next Steps

1. **Build APK**: `flutter build apk --release`
2. **Install**: `adb install -r build/app/outputs/flutter-apk/app-release.apk`
3. **Test**: Point camera at chessboard and verify predictions
4. **Review**: Download logs and images to verify quality
5. **Optimize**: Adjust parameters based on your specific board and lighting

---

**Questions?** Check the Android logcat output for "BoardEngine" debug messages.
