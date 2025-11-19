# Model Inference Restoration Summary

## Overview
Successfully restored the Chess Moves Tracking Android app to use **live model inference** instead of random FEN generation, with enhanced logging and image saving capabilities.

## Changes Made

### 1. **Restored Model Inference** (`BoardEngine.kt`)
   - **Location**: `processYuvAndGetFen()` method (lines ~155-177)
   - **Before**: Generated random FEN positions every second for testing
   - **After**: 
     - Uncommented `classify64(warp)` to run actual TensorFlow Lite model inference
     - Uncommented `toFen(labels64)` to convert model predictions to FEN notation
     - Restored stability check logic using `minStableFrames` parameter (default: 2)
     - Only returns FEN when a stable position change is detected

### 2. **Enhanced Logging Infrastructure**

   #### LogEntry Data Class (lines ~55-63)
   - Added `imageFile` parameter to store path to saved frame image
   - Tracks: timestamp, frame number, gameId, piece labels, FEN, candidate position, stability count, and whether it's a stable change

   #### Frame Image Saving (logPrediction method, lines ~600-630)
   - **Automatically saves the processed board image** for every frame to `chess_samples/` directory
   - Image files named: `frame_{frameNumber}_{timestamp}.png`
   - Images are referenced in log entries for easy review and debugging
   - Silent error handling - doesn't crash if image save fails

   #### Enhanced Log File Output (saveLogs method, lines ~632-665)
   - Added generation timestamp
   - Added sample directory path for easy access to saved images
   - Includes frame image paths in each log entry
   - Improved formatting with wider separators
   - Added logging output to Android system log

### 3. **Removed Temporary Testing Code**
   - Deleted `generateRandomFen()` helper function
   - Deleted `fenToLabels64()` helper function (no longer needed)
   - Removed temporary variables: `lastRandomFenTime`, `lastRandomFen`

## Directory Structure

The app now saves files to the following locations:

```
/data/data/com.example.chess_moves_tracking/files/
├── chess_logs/              # Log files
│   └── game_{gameId}_{timestamp}.log  or  predictions_{timestamp}.log
│
└── chess_samples/           # Sample images for review
    ├── frame_{n}_{timestamp}.png    # Individual board frames
    ├── board_sample_{n}.png         # Every 10th full board
    ├── piece_{r}_{c}_sample_{n}.png # Piece ROI samples
    └── scaled_{n}.png               # Debug scaled images
```

## How to Use

### Setting a Game ID (for organization)
```dart
// From Flutter side
await platform.invokeMethod('setGameId', {'gameId': 'game_123'});
```

### Saving Logs After Recording
```dart
// From Flutter side
final logPath = await platform.invokeMethod('saveLogs');
```

### Log File Format
The log file contains detailed information for each prediction:

```
Chess Board Detection Log
Game ID: game_123
Generated: 2025-11-18 14:30:45
Total Entries: 458
Sample Directory: /data/data/com.example.chess_moves_tracking/files/chess_samples/
====================================================================================================

Timestamp: 2025-11-18 14:30:01.234
Frame: 100
Game ID: game_123
Labels (64 squares): r,n,b,q,k,b,n,r,p,p,p,p,p,p,p,p,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,.,P,P,P,P,P,P,P,P,R,N,B,Q,K,B,N,R
FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1
Candidate: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1
Stable Count: 2
Stable Change: true
Frame Image: /data/data/com.example.chess_moves_tracking/files/chess_samples/frame_100_1700318401234.png
----------------------------------------------------------------------------------------------------
```

## Model Configuration

- **Model File**: `pieces_int8.tflite` (quantized INT8 model)
- **Input Size**: Dynamic (configured in the interpreter)
- **Output**: 13 labels per square (12 pieces + empty square)
- **Processing**: Every frame is downscaled to max 640px for efficiency
- **Board Warping**: 512×512 perspective-corrected board image
- **Inference Speed**: Optimized with 3 threads on CPU (XNNPACK)

## Stability Mechanism

The app uses a stability check to avoid false positives:
- Requires `minStableFrames` (default: 2) consecutive frames with the same position
- Only returns/broadcasts the FEN when this threshold is met
- Prevents rapid flickering due to individual misclassified frames

## Debugging

To review what the model is seeing:
1. **Check the log file** at `/data/data/com.example.chess_moves_tracking/files/chess_logs/`
2. **View saved frame images** at `/data/data/com.example.chess_moves_tracking/files/chess_samples/`
3. **Check Android logcat** for "BoardEngine" tags for real-time debugging

## Testing Tips

1. **Verify Model Loading**: Check if the app starts without crashing - if it does, `pieces_int8.tflite` is found and loaded
2. **Check Board Detection**: The app saves scaled images every 100 frames - if the board isn't detected, check these images
3. **Review Predictions**: Look at `frame_*.png` images with corresponding log entries to understand prediction quality
4. **Monitor Stability**: The "Stable Change" flag shows when the position stabilized

## Known Considerations

- Image saving happens synchronously during inference - very large number of images could impact performance
- If storage becomes an issue, you can:
  - Reduce sampling frequency (modify `sampleCounter` conditionals)
  - Clear the `chess_samples/` directory periodically
  - Only enable detailed logging for specific game sessions

## Next Steps

1. **Test on your device** with the new model
2. **Review the log files** to verify detection quality
3. **Adjust `minStableFrames`** if the board is flickering or too slow to respond
4. **Fine-tune stability settings** based on your chess board lighting conditions
