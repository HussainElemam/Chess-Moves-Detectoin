# Debugging Chess Board Detection - Sample Collection

## Overview
The app now automatically saves sample images of the detected chess board and individual piece squares to help you debug the model accuracy and detection pipeline.

## Where Are The Samples Saved?

Samples are saved to the device's app-specific external storage directory:
```
/sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/
```

## What Gets Saved?

### 1. **Full Board Samples**
- **Files**: `board_sample_*.png`
- **Saved Every**: 10 frames
- **Size**: 640×640 pixels (the warped, perspective-corrected board)
- **Purpose**: Shows what the model sees after perspective correction and color normalization
- **What to look for**:
  - Is the board correctly detected and warped?
  - Are the colors normalized properly (white squares should be light, black squares dark)?
  - Is the perspective correction working?

### 2. **Individual Piece Squares**
- **Files**: `piece_{row}_{col}_sample_*.png`
- **Saved Every**: 10 frames (but only for top-left 2×2 squares to save space)
- **Size**: 96×96 pixels (resized to model input size)
- **Purpose**: Shows what each piece square looks like after extraction and resizing
- **Rows & Cols**: 0-7 (0 = top-left, 7 = bottom-right of the board)
- **What to look for**:
  - Are the squares properly extracted with correct inset?
  - Are pieces visible or is there too much background?
  - Is the resizing distorting the pieces?

## How to Retrieve Samples

### Option 1: Using ADB (Recommended)
```bash
# List the samples
adb shell ls -la /sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/

# Pull all samples to your computer
adb pull /sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/ ./chess_samples/

# Or pull just board samples
adb pull /sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/board_sample*.png ./

# Or pull just a few piece samples
adb pull /sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/piece_0_*.png ./
```

### Option 2: Using Android Studio's Device File Explorer
1. Open Android Studio
2. Go to: `View → Tool Windows → Device File Explorer`
3. Navigate to: `data/data/com.example.chess_moves_tracking/files/chess_samples/`
4. Right-click on files and select "Save As"

### Option 3: Using File Manager (on rooted devices)
Use your device's file manager to navigate to the directory and copy files to a cloud storage service.

## Analyzing the Samples

### Questions to Ask While Reviewing Samples:

**For Board Samples (`board_sample_*.png`):**
1. ✅ Is the entire chess board visible and not cut off?
2. ✅ Are the 8×8 squares clearly visible?
3. ✅ Is the perspective correction making the board look flat/top-down?
4. ✅ Are colors normalized (light squares lighter, dark squares darker)?
5. ✅ Is the board properly oriented (top-left should be dark if facing white)?
6. ❌ Is there any glare, shadow, or lighting issue?
7. ❌ Are pieces too dark/bright or blurry?

**For Piece Samples (`piece_*_sample_*.png`):**
1. ✅ Can you clearly see the piece in the square?
2. ✅ Is the background (empty squares) visible but not dominating?
3. ✅ Is the piece centered in the 96×96 image?
4. ✅ Is the piece recognizable (can you tell what piece it is)?
5. ❌ Is the piece too small or truncated?
6. ❌ Is there too much background noise?
7. ❌ Is the image blurry or distorted?

### Interpreting Results:

**If board samples look bad:**
- 🔴 **Issue**: Board not detected properly
- 🔴 **Issue**: Wrong perspective transformation
- 🔴 **Solution**: Check lighting, board orientation, or adjust `detectQuad()` thresholds

**If piece samples look bad:**
- 🔴 **Issue**: Inset extraction is too aggressive (pieces are cut off)
- 🔴 **Issue**: Resizing is distorting pieces
- 🔴 **Solution**: Adjust `insetFrac` (currently 0.08 = 8%) to 0.05 or 0.10
- 🔴 **Solution**: Verify the piece images match what your model was trained on

**If pieces are unrecognized but look good:**
- 🟡 **Issue**: Model accuracy problem (not a code issue)
- 🟡 **Solution**: Retrain your model or use different training data
- 🟡 **Solution**: Check that piece samples visually match your training data

## Modifying Sampling Parameters

To change the sampling frequency or behavior, edit `BoardEngine.kt`:

```kotlin
// Line ~48 (in class definition)
private var sampleCounter = 0

// Line ~267 (in classify64 function)
if (sampleCounter % 10 == 0) {  // Change 10 to 5 for more samples, 20 for fewer
    // Save board sample
}

// Line ~280 (in classify64 function) 
if (sampleCounter % 10 == 0 && r < 2 && c < 2) {  // Change r < 2 && c < 2 to r < 4 && c < 4 for more piece samples
    // Save piece sample
}
```

## Storage Considerations

Each sample takes ~500KB-1MB of space:
- Board sample (640×640): ~400KB PNG
- Piece sample (96×96): ~50KB PNG

Saving every 10 frames = ~8 samples per second per type = **~4MB per second**

If you run the app for 1 minute, expect ~240MB of samples. The app saves to **external app storage** which has plenty of space, but be aware if running long tests.

## Clearing Samples

To clean up old samples:
```bash
adb shell rm -rf /sdcard/Android/data/com.example.chess_moves_tracking/files/chess_samples/*
```

Or just reinstall the app (data will be cleared).

## Troubleshooting

**"Permission denied" when saving samples:**
- Make sure WRITE_EXTERNAL_STORAGE permission is granted
- Go to Settings → Apps → Chess Moves Tracking → Permissions → Storage

**"No samples appearing after running app:"**
- The sampling only starts when a board is successfully detected
- Make sure the app is showing "Position detected" in the UI
- Check the samples directory using ADB to confirm it exists

**"Samples directory not found:**
- Run the app at least once with a detected board
- Use ADB to check: `adb shell ls -la /sdcard/Android/data/com.example.chess_moves_tracking/files/`

## Next Steps for Model Improvement

1. **Collect 100-200 sample boards** from different:
   - Lighting conditions (bright, dim, under table lamp)
   - Camera angles (overhead, angled, far away)
   - Board types (wooden, plastic, marble, digital)
   - Piece styles (Staunton, minimal, decorative)

2. **Organize samples** by piece type and square color:
   - `piece_train/empty_light/sample_1.png`
   - `piece_train/king_white/sample_1.png`
   - `piece_train/pawn_black/sample_2.png`
   - etc.

3. **Retrain your TensorFlow Lite model** with this new data for better accuracy

4. **Test again** and compare performance
