# Quick Reference: Model Restoration Changes

## What Changed

Your Android Kotlin code has been updated to:

✅ **Restore Live Model Inference** - Uses your new TensorFlow Lite model instead of generating random positions  
✅ **Enable Automatic Image Logging** - Saves every processed board frame for review  
✅ **Add Detailed Logging** - Creates comprehensive log files with model predictions and image references  

## Key Files Modified

- `android/app/src/main/kotlin/com/example/chess_moves_tracking/BoardEngine.kt`

## How It Works Now

### Processing Pipeline
```
Live Video Frame
    ↓
YUV420 → BGR (Color conversion)
    ↓
Resize & Downscale
    ↓
Detect Chessboard Quadrilateral
    ↓
Perspective Warp (512×512)
    ↓
Run TensorFlow Lite Model (pieces_int8.tflite)
    ↓
Get 64 Piece Predictions
    ↓
Convert to FEN Notation
    ↓
Stability Check (2+ consecutive identical frames)
    ↓
Save Frame Image & Log Entry
    ↓
Return FEN (if stable change detected)
```

## Output Files

### Log Files
**Location**: `chess_logs/` directory
- **Filename**: `game_{gameId}_{timestamp}.log` (if gameId set) or `predictions_{timestamp}.log`
- **Contains**: Frame-by-frame predictions with image references

### Sample Images
**Location**: `chess_samples/` directory
- **`frame_*.png`** - Every processed board (with image path in log)
- **`board_sample_*.png`** - Every 10th full board for verification
- **`piece_*.png`** - Individual piece crops for debugging
- **`scaled_*.png`** - Pre-processing check images (every 100 frames)

## Model Details

| Parameter | Value |
|-----------|-------|
| Model File | `pieces_int8.tflite` |
| Model Type | Quantized INT8 (fast) |
| Input Size | Dynamic |
| Output Classes | 13 (12 pieces + empty) |
| Board Size | 512×512 pixels |
| Processing Threads | 3 (CPU optimized) |
| Min Stable Frames | 2 (configurable) |

## Stability Mechanism

The model only returns a FEN position when:
1. The same position appears in **2 consecutive processed frames** (configurable via `minStableFrames`)
2. This position is **different from the previous stable position**

This prevents:
- Flickering due to single-frame misclassifications
- False positives from transient board states
- Rapid changes that don't represent actual moves

## Testing Your Setup

### Step 1: Verify Model Loading
- Start the app
- If it crashes immediately, the model file is missing or corrupted
- Check that `pieces_int8.tflite` exists in `android/app/src/main/assets/`

### Step 2: Check Board Detection
- Point camera at chessboard
- App saves `scaled_100.png`, `scaled_200.png`, etc. every 100 frames
- Review these images in the `chess_samples/` directory
- If board isn't detected, lighting or perspective may be an issue

### Step 3: Validate Predictions
- Let the app run for 30+ seconds on a chessboard
- Call `saveLogs()` from Flutter
- Check the generated log file and corresponding frame images
- Verify FEN notation matches the actual board position

### Step 4: Adjust Stability if Needed
- If board flickers: Increase `minStableFrames` (currently 2)
- If too slow to detect moves: Decrease `minStableFrames`
- Edit line ~24 in `BoardEngine.kt`

## Common Issues & Solutions

### Issue: App crashes on startup
**Solution**: Verify `pieces_int8.tflite` is in `android/app/src/main/assets/`

### Issue: No frames being processed
**Solution**: Check that camera frames are being sent from Flutter side with correct dimensions

### Issue: Wrong positions detected
**Solution**: 
1. Review `frame_*.png` images in chess_samples/
2. Check board lighting and perspective
3. Verify the model was trained on similar board images
4. Consider adjusting board detection threshold (line ~220)

### Issue: Storage full
**Solution**: 
- Log files: Safe to delete old log files
- Sample images: Can reduce sampling frequency or clear periodically
- Consider archiving images for important games

## Integration with Flutter

### Setting Game ID
```dart
const platform = MethodChannel('vision_bridge');
await platform.invokeMethod('setGameId', {'gameId': 'my_game_123'});
```

### Saving Logs
```dart
try {
  final logPath = await platform.invokeMethod('saveLogs');
  print('Logs saved to: $logPath');
} catch (e) {
  print('Error saving logs: $e');
}
```

### Clearing Logs
```dart
await platform.invokeMethod('clearLogs');
```

## Performance Tips

1. **Frame Processing Rate**: Currently processes every 3rd frame (`processEvery: 3`)
2. **Model Optimization**: Uses INT8 quantization for speed
3. **Threading**: Background thread for inference to avoid UI lag
4. **Image Saving**: Optional, can disable by removing `Imgcodecs.imwrite()` calls if storage is an issue

## Model Training Considerations

Your new model should:
- Accept RGB input (3 channels)
- Output 13 classes per square (12 pieces + empty)
- Be quantized as INT8 for optimal performance
- Be saved as `.tflite` format in assets

## Reverting Changes

All changes are isolated to `BoardEngine.kt`. If you need to revert:
1. The random FEN generation code is removed (not needed anymore)
2. Restore from git: `git checkout -- android/app/src/main/kotlin/com/example/chess_moves_tracking/BoardEngine.kt`

---

**Ready to test!** 🎉 Rebuild your APK and test on a real chessboard.
