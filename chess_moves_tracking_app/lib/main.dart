import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

late List<CameraDescription> cameras;

// Server configuration - change this to your server URL
// const String serverUrl = 'http://localhost:3000';
// For Android emulator, use: 'http://10.0.2.2:3000'
// For physical device, use your computer's IP: 'http://192.168.x.x:3000'
const String serverUrl = 'http://192.168.142.206:3000';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  cameras = await availableCameras();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Chess Moves Tracking',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple), useMaterial3: true),
      home: const ChessBoardTracker(),
    );
  }
}

class ChessBoardTracker extends StatefulWidget {
  const ChessBoardTracker({super.key});

  @override
  State<ChessBoardTracker> createState() => _ChessBoardTrackerState();
}

class _ChessBoardTrackerState extends State<ChessBoardTracker> {
  late CameraController _cameraController;
  String _currentFen = 'Not detected yet';
  String _status = 'Initializing...';
  bool _isInitialized = false;
  int _frameCounter = 0;
  int _errorCount = 0;
  int _detectionCount = 0;
  DateTime? _lastDetectionTime;
  bool _showFlash = false;
  String _processingStats = 'Processing...';

  // Game session management
  String? _gameId;
  bool _isGameActive = false;
  bool _isCreatingGame = false;
  String? _serverError;

  static const platform = MethodChannel('vision_bridge');

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    try {
      if (cameras.isEmpty) {
        setState(() {
          _status = 'No cameras found';
        });
        return;
      }

      _cameraController = CameraController(
        cameras.first,
        ResolutionPreset.medium, // Changed from high to medium to reduce memory
        enableAudio: false,
      );

      await _cameraController.initialize();

      // Start processing frames with a longer delay
      await _cameraController.startImageStream(_processImage);

      setState(() {
        _isInitialized = true;
        _status = 'Camera initialized';
      });
    } catch (e) {
      setState(() {
        _status = 'Camera initialization error: $e';
      });
      debugPrint('Error initializing camera: $e');
    }
  }

  Future<void> _processImage(CameraImage image) async {
    try {
      // Skip frames to reduce memory pressure
      _frameCounter++;
      if (_frameCounter % 10 != 0) return; // Process every 10th frame

      // Convert CameraImage to the format expected by native code
      final result = await platform.invokeMethod<String?>('inferFenFromYUV420', {
        'width': image.width,
        'height': image.height,
        'bytesY': image.planes[0].bytes,
        'bytesU': image.planes[1].bytes,
        'bytesV': image.planes[2].bytes,
        'strideY': image.planes[0].bytesPerRow,
        'strideU': image.planes[1].bytesPerRow,
        'strideV': image.planes[2].bytesPerRow,
        'pixelStrideU': image.planes[1].bytesPerPixel ?? 1,
        'pixelStrideV': image.planes[2].bytesPerPixel ?? 1,
        'processEvery': 3, // Process every 3rd frame for performance
      });

      if (result != null && result.isNotEmpty) {
        _detectionCount++;
        _lastDetectionTime = DateTime.now();
        _showFlash = true;

        // Clear flash after 200ms
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted) {
            setState(() {
              _showFlash = false;
            });
          }
        });

        setState(() {
          _currentFen = result;
          _status = 'Position detected (#$_detectionCount)';
          _processingStats = 'Frame: $_frameCounter | Detections: $_detectionCount | Errors: $_errorCount';
        });
        debugPrint('Detection #$_detectionCount - FEN: $result');

        // Send to server if game is active
        if (_isGameActive && _gameId != null) {
          _sendPositionToServer(result);
        }
      } else {
        setState(() {
          _processingStats = 'Frame: $_frameCounter | Detections: $_detectionCount | Errors: $_errorCount (waiting...)';
        });
      }
    } catch (e) {
      debugPrint('Error processing frame: $e');
      // Only show error after several occurrences to avoid spam
      _errorCount++;
      if (_errorCount % 5 == 0) {
        setState(() {
          _status = 'Error: Processing frame ($_errorCount errors)';
          _processingStats = 'Frame: $_frameCounter | Detections: $_detectionCount | Errors: $_errorCount';
        });
      }
    }
  }

  Future<void> _createGame() async {
    setState(() {
      _isCreatingGame = true;
      _serverError = null;
    });

    try {
      final response = await http
          .post(Uri.parse('$serverUrl/api/games'), headers: {'Content-Type': 'application/json'})
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          _gameId = data['gameId'];
          _isGameActive = true;
          _isCreatingGame = false;
          _status = 'Game active - Position detected (#$_detectionCount)';
        });
        debugPrint('Game created: $_gameId');

        // Set game ID in Kotlin for logging
        try {
          await platform.invokeMethod('setGameId', {'gameId': _gameId});
        } catch (e) {
          debugPrint('Error setting game ID in Kotlin: $e');
        }

        // Clear previous logs when starting new game
        try {
          await platform.invokeMethod('clearLogs');
        } catch (e) {
          debugPrint('Error clearing logs: $e');
        }

        // // TEMPORARY: Send initial starting chess position for testing
        // const startingFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
        // await _sendPositionToServer(startingFen);
        // setState(() {
        //   _currentFen = startingFen;
        // });
      } else {
        throw Exception('Failed to create game: ${response.statusCode}');
      }
    } catch (e) {
      setState(() {
        _isCreatingGame = false;
        _serverError = 'Failed to create game: $e';
      });
      debugPrint('Error creating game: $e');
    }
  }

  Future<void> _sendPositionToServer(String fen) async {
    if (_gameId == null || !_isGameActive) {
      debugPrint('Not sending position - gameId: $_gameId, isGameActive: $_isGameActive');
      return;
    }

    try {
      debugPrint('Sending position to server: $fen for game: $_gameId');
      final response = await http
          .post(
            Uri.parse('$serverUrl/api/games/$_gameId/position'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'fen': fen}),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        debugPrint('Position sent to server successfully: $fen');
        setState(() {
          _serverError = null;
        });
      } else {
        debugPrint('Failed to send position: ${response.statusCode} - ${response.body}');
        throw Exception('Failed to send position: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('Error sending position to server: $e');
      setState(() {
        _serverError = 'Server error: $e';
      });
    }
  }

  Future<void> _stopGame() async {
    if (!_isGameActive || _gameId == null) return;

    setState(() {
      _isGameActive = false;
    });

    // Save logs in Kotlin
    try {
      final logPath = await platform.invokeMethod<String>('saveLogs');
      if (logPath != null) {
        debugPrint('Logs saved to: $logPath');
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Logs saved to: $logPath'), duration: const Duration(seconds: 3)));
      } else {
        debugPrint('No logs to save');
      }
    } catch (e) {
      debugPrint('Error saving logs: $e');
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Error saving logs: $e'), duration: const Duration(seconds: 2)));
    }

    // Clear game ID in Kotlin
    try {
      await platform.invokeMethod('setGameId', {'gameId': null});
    } catch (e) {
      debugPrint('Error clearing game ID in Kotlin: $e');
    }

    setState(() {
      _gameId = null;
      _status = 'Game stopped - Position detected (#$_detectionCount)';
    });
  }

  void _copyGameId() {
    if (_gameId != null) {
      Clipboard.setData(ClipboardData(text: _gameId!));
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Game ID copied to clipboard'), duration: Duration(seconds: 2)));
    }
  }

  @override
  void dispose() {
    _cameraController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chess Moves Tracking'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          if (!_isGameActive)
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: ElevatedButton(
                onPressed: _isCreatingGame ? null : _createGame,
                style: ElevatedButton.styleFrom(backgroundColor: Colors.green, foregroundColor: Colors.white),
                child: _isCreatingGame
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : const Text('Start Game'),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.all(8.0),
              child: ElevatedButton(
                onPressed: _stopGame,
                style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
                child: const Text('Stop Game'),
              ),
            ),
        ],
      ),
      body: _isInitialized
          ? Stack(
              children: [
                // Camera preview
                CameraPreview(_cameraController),
                // Flash overlay when detection occurs
                if (_showFlash) Container(color: Colors.yellow.withOpacity(0.5)),
                // Top status indicator
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    color: Colors.black87,
                    padding: const EdgeInsets.all(12.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              _status,
                              style: TextStyle(
                                color: _currentFen == 'Not detected yet' ? Colors.orange : Colors.greenAccent,
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: _currentFen == 'Not detected yet' ? Colors.orange : Colors.green,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                'Detections: $_detectionCount',
                                style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _processingStats,
                          style: const TextStyle(color: Colors.white70, fontSize: 10, fontFamily: 'Courier'),
                        ),
                      ],
                    ),
                  ),
                ),
                // Bottom overlay with detected position
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    color: Colors.black87,
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Game ID section
                        if (_isGameActive && _gameId != null) ...[
                          Container(
                            padding: const EdgeInsets.all(8.0),
                            decoration: BoxDecoration(
                              color: Colors.green[900],
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: Colors.green, width: 2),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Text('Game ID:', style: TextStyle(color: Colors.white70, fontSize: 10)),
                                      const SizedBox(height: 4),
                                      Text(
                                        _gameId!,
                                        style: const TextStyle(
                                          color: Colors.greenAccent,
                                          fontSize: 12,
                                          fontFamily: 'Courier',
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.copy, color: Colors.white, size: 20),
                                  onPressed: _copyGameId,
                                  tooltip: 'Copy Game ID',
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                        ],
                        if (_serverError != null) ...[
                          Container(
                            padding: const EdgeInsets.all(8.0),
                            decoration: BoxDecoration(color: Colors.red[900], borderRadius: BorderRadius.circular(4)),
                            child: Text(_serverError!, style: const TextStyle(color: Colors.redAccent, fontSize: 10)),
                          ),
                          const SizedBox(height: 8),
                        ],
                        if (_lastDetectionTime != null)
                          Text(
                            'Last updated: ${_lastDetectionTime?.toString().split('.')[0]}',
                            style: const TextStyle(color: Colors.white70, fontSize: 10),
                          ),
                        const SizedBox(height: 8),
                        const Text('Current Position (FEN):', style: TextStyle(color: Colors.white70, fontSize: 12)),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.all(8.0),
                          decoration: BoxDecoration(
                            color: Colors.grey[800],
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: _showFlash ? Colors.yellow : Colors.grey, width: 2),
                          ),
                          child: Text(
                            _currentFen,
                            style: const TextStyle(
                              color: Colors.green,
                              fontSize: 14,
                              fontFamily: 'Courier',
                              fontWeight: FontWeight.w500,
                            ),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            )
          : Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [const CircularProgressIndicator(), const SizedBox(height: 16), Text(_status)],
              ),
            ),
    );
  }
}
