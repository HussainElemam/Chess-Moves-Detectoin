# Chess Live Web Interface

Web interface for viewing live chess positions detected by the Flutter app.

## Usage

1. Make sure the backend server is running (see `../server/README.md`)

2. Open `index.html` in a web browser, or serve it using a local web server:
   ```bash
   # Using Python
   python -m http.server 8000
   
   # Using Node.js (if you have http-server installed)
   npx http-server -p 8000
   ```

3. Enter the game ID from the Flutter app and click "Connect"

4. The chess board will update in real-time as positions are detected

## Features

- Real-time position updates via WebSocket
- Displays current FEN position
- Shows move count and last update time
- Uses Lichess embed for board visualization

## Notes

- The web interface connects to the server running on port 3000 by default
- For production, you may want to configure the server URL in `app.js`
- If the Lichess embed doesn't work for your use case, you can replace it with a chess board library like chessboard.js or chessground

