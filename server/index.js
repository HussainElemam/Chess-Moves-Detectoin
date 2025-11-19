const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const cors = require('cors');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Middleware
app.use(cors());
app.use(express.json());

// In-memory game storage
const games = new Map();

// Generate a short 6-character game ID
function generateGameId() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let gameId = '';
  for (let i = 0; i < 6; i++) {
    gameId += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  
  // Ensure uniqueness (regenerate if already exists)
  if (games.has(gameId)) {
    return generateGameId();
  }
  
  return gameId;
}

// WebSocket connection handler
wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const gameId = url.searchParams.get('gameId');

  if (!gameId) {
    ws.close(1008, 'Missing gameId parameter');
    return;
  }

  if (!games.has(gameId)) {
    ws.close(1008, 'Game not found');
    return;
  }

  const game = games.get(gameId);
  
  // Send current position immediately on connection
  if (game.currentFen) {
    console.log(`Sending current position to client for game ${gameId}: ${game.currentFen}`);
    ws.send(JSON.stringify({
      type: 'position',
      fen: game.currentFen,
      timestamp: game.lastUpdate
    }));
  } else {
    console.log(`No current position for game ${gameId}`);
  }

  // Store WebSocket connection for this game
  if (!game.connections) {
    game.connections = new Set();
  }
  game.connections.add(ws);

  ws.on('close', () => {
    if (game.connections) {
      game.connections.delete(ws);
    }
  });

  ws.on('error', (error) => {
    console.error('WebSocket error:', error);
  });
});

// Broadcast position update to all connected clients for a game
function broadcastPosition(gameId, fen) {
  const game = games.get(gameId);
  if (!game || !game.connections) {
    console.log(`No connections for game ${gameId}`);
    return;
  }

  const message = JSON.stringify({
    type: 'position',
    fen: fen,
    timestamp: Date.now()
  });

  let sentCount = 0;
  game.connections.forEach((ws) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(message);
      sentCount++;
    }
  });
  console.log(`Broadcasted to ${sentCount} clients for game ${gameId}`);
}

// REST API Routes

// Create a new game session
app.post('/api/games', (req, res) => {
  const gameId = generateGameId();
  const game = {
    gameId: gameId,
    currentFen: null,
    moveHistory: [],
    createdAt: Date.now(),
    lastUpdate: null,
    connections: new Set()
  };

  games.set(gameId, game);

  // Clean up old games (older than 24 hours)
  const now = Date.now();
  for (const [id, g] of games.entries()) {
    if (now - g.createdAt > 24 * 60 * 60 * 1000) {
      if (g.connections) {
        g.connections.forEach(ws => ws.close());
      }
      games.delete(id);
    }
  }

  res.json({ gameId: gameId });
});

// Receive FEN position from Flutter app
app.post('/api/games/:gameId/position', (req, res) => {
  const { gameId } = req.params;
  const { fen } = req.body;

  if (!fen || typeof fen !== 'string') {
    return res.status(400).json({ error: 'Invalid FEN string' });
  }

  if (!games.has(gameId)) {
    return res.status(404).json({ error: 'Game not found' });
  }

  const game = games.get(gameId);
  const previousFen = game.currentFen;
  game.currentFen = fen;
  game.lastUpdate = Date.now();

  // Add to move history if position changed
  if (previousFen !== fen) {
    game.moveHistory.push({
      fen: fen,
      timestamp: game.lastUpdate
    });
  }

  // Broadcast to all connected WebSocket clients
  console.log(`Broadcasting position for game ${gameId}: ${fen}`);
  broadcastPosition(gameId, fen);

  res.json({ success: true, gameId: gameId });
});

// Get current game state (for debugging/testing)
app.get('/api/games/:gameId', (req, res) => {
  const { gameId } = req.params;

  if (!games.has(gameId)) {
    return res.status(404).json({ error: 'Game not found' });
  }

  const game = games.get(gameId);
  res.json({
    gameId: game.gameId,
    currentFen: game.currentFen,
    moveHistoryCount: game.moveHistory.length,
    createdAt: game.createdAt,
    lastUpdate: game.lastUpdate,
    connectedClients: game.connections ? game.connections.size : 0
  });
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', activeGames: games.size });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, '0.0.0.0', () => {
  console.log(`Chess Live Server running on port ${PORT}`);
  console.log(`WebSocket endpoint: ws://0.0.0.0:${PORT}/ws`);
});

