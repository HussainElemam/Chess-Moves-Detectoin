# Chess Live Server

Backend server for the chess live position tracking system. Handles game session management and real-time position updates via WebSocket.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start the server:
```bash
npm start
```

The server will run on `http://localhost:3000` by default.

## Environment Variables

- `PORT` - Server port (default: 3000)

## API Endpoints

### POST /api/games
Create a new game session.

**Response:**
```json
{
  "gameId": "uuid-here"
}
```

### POST /api/games/:gameId/position
Send a FEN position update for a game.

**Request Body:**
```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
}
```

**Response:**
```json
{
  "success": true,
  "gameId": "uuid-here"
}
```

### GET /api/games/:gameId
Get current game state (for debugging).

**Response:**
```json
{
  "gameId": "uuid-here",
  "currentFen": "...",
  "moveHistoryCount": 5,
  "createdAt": 1234567890,
  "lastUpdate": 1234567890,
  "connectedClients": 2
}
```

### GET /health
Health check endpoint.

## WebSocket

Connect to `ws://localhost:3000/ws?gameId=<gameId>` to receive real-time position updates.

**Message Format:**
```json
{
  "type": "position",
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "timestamp": 1234567890
}
```

## Notes

- Games are stored in memory and will be cleaned up after 24 hours of inactivity
- Each game can have multiple WebSocket connections
- Position updates are broadcast to all connected clients for that game

