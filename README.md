# Chess Live Position Tracking

A complete system for tracking chess positions in real-time using computer vision and displaying them on a web interface.

## Components

1. **Flutter App** (`chess_moves_tracking_app/`) - Mobile app that uses camera and TensorFlow Lite to detect chess pieces and generate FEN positions
2. **Backend Server** (`server/`) - Node.js/Express server that manages game sessions and broadcasts position updates via WebSocket
3. **Web Interface** (`web_interface/`) - HTML/JavaScript web app that displays chess positions in real-time using Lichess embed

## Quick Start

### 1. Start the Backend Server

```bash
cd server
npm install
npm start
```

The server will run on `http://localhost:3000`

### 2. Configure Flutter App Server URL

Edit `chess_moves_tracking_app/lib/main.dart` and update the `serverUrl` constant:

```dart
const String serverUrl = 'http://localhost:3000';
// For Android emulator: 'http://10.0.2.2:3000'
// For physical device: 'http://YOUR_COMPUTER_IP:3000'
```

### 3. Run the Flutter App

```bash
cd chess_moves_tracking_app
flutter run
```

### 4. Start a Game

1. Open the Flutter app
2. Click "Start Game" button in the app bar
3. Copy the generated Game ID
4. The app will automatically send detected positions to the server

### 5. View on Web Interface

1. Open `web_interface/index.html` in a browser (or serve it with a web server)
2. Enter the Game ID from the Flutter app
3. Click "Connect"
4. Watch the chess board update in real-time!

## Architecture

- **Flutter App**: Detects chess positions using camera + TFLite model, sends FEN to server
- **Backend Server**: Manages game sessions, receives FEN updates, broadcasts via WebSocket
- **Web Interface**: Connects to server via WebSocket, displays positions using Lichess embed

## Network Configuration

### For Android Emulator
- Use `http://10.0.2.2:3000` (special IP that maps to host machine's localhost)

### For Physical Device
- Find your computer's IP address:
  ```bash
  # Linux/Mac
  ip addr show | grep "inet " | grep -v 127.0.0.1
  
  # Windows
  ipconfig
  ```
- Use `http://YOUR_IP:3000` in the Flutter app
- Make sure your device and computer are on the same network
- Ensure firewall allows connections on port 3000

## Troubleshooting

- **Can't connect from Flutter app**: Check server URL and ensure server is running
- **Web interface shows "Connection error"**: Verify server is running and WebSocket endpoint is accessible
- **Positions not updating**: Check that game ID matches between Flutter app and web interface

## License

See individual component directories for license information.

