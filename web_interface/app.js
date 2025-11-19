let ws = null;
let moveCount = 0;
let board = null;
let serverUrl = 'http://localhost:3000';

// Get server URL from environment or use default
if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    // If not localhost, assume server is on same host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    serverUrl = `${wsProtocol}//${window.location.hostname}:3000`;
}

function updateStatus(message, type) {
    const statusEl = document.getElementById('status');
    statusEl.textContent = message;
    statusEl.className = `status ${type}`;
}

function showError(message) {
    const errorEl = document.getElementById('errorMessage');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
    setTimeout(() => {
        errorEl.style.display = 'none';
    }, 5000);
}

function hideError() {
    document.getElementById('errorMessage').style.display = 'none';
}

function connectToGame() {
    const gameId = document.getElementById('gameIdInput').value.trim();
    
    if (!gameId) {
        showError('Please enter a game ID');
        return;
    }

    // Disconnect existing connection
    if (ws) {
        ws.close();
        ws = null;
    }

    updateStatus('Connecting...', 'connecting');
    hideError();

    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsUrl;
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        wsUrl = `ws://localhost:3000/ws?gameId=${gameId}`;
    } else {
        wsUrl = `${wsProtocol}//${window.location.hostname}:3000/ws?gameId=${gameId}`;
    }

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        updateStatus('Connected', 'connected');
        const container = document.getElementById('boardContainer');
        container.style.display = 'block';
        
        // Use the globally initialized board or initialize if needed
        if (window.chessBoardInstance) {
            board = window.chessBoardInstance;
            console.log('Using existing board instance');
        } else if (!board) {
            console.log('Initializing new board instance');
            initializeBoard();
        }
        
        // Ensure board is visible and properly sized
        setTimeout(() => {
            if (board || window.chessBoardInstance) {
                const boardInstance = board || window.chessBoardInstance;
                // Refresh board to ensure it's visible
                if (boardInstance && typeof boardInstance.position === 'function') {
                    const currentPos = boardInstance.position();
                    boardInstance.position(currentPos);
                }
            }
        }, 100);
    };

    ws.onmessage = (event) => {
        try {
            console.log('WebSocket message received:', event.data);
            const data = JSON.parse(event.data);
            console.log('Parsed data:', data);
            if (data.type === 'position' && data.fen) {
                console.log('Updating board with FEN:', data.fen);
                updateBoard(data.fen);
                moveCount++;
                document.getElementById('moveCount').textContent = moveCount;
                
                if (data.timestamp) {
                    const date = new Date(data.timestamp);
                    document.getElementById('lastUpdate').textContent = date.toLocaleTimeString();
                }
            } else {
                console.warn('Unexpected message format:', data);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error, 'Raw data:', event.data);
            showError('Error processing position update');
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        showError('Connection error. Make sure the server is running.');
        updateStatus('Connection error', 'disconnected');
    };

    ws.onclose = () => {
        updateStatus('Disconnected', 'disconnected');
        if (ws) {
            ws = null;
        }
    };
}

function initializeBoard() {
    // Wait for jQuery and chessboard.js to be loaded with retries
    let attempts = 0;
    const maxAttempts = 20;
    
    const tryInit = () => {
        attempts++;
        if (typeof jQuery !== 'undefined' && typeof Chessboard !== 'undefined') {
            try {
                // Initialize chessboard.js
                board = Chessboard('chessBoard', {
                    position: 'start',
                    draggable: false,
                    pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',
                    onDragStart: function() { return false; } // Disable dragging
                });
                console.log('Board initialized successfully');
            } catch (error) {
                console.error('Error initializing board:', error);
                showError('Error initializing chess board: ' + error.message);
            }
        } else if (attempts < maxAttempts) {
            setTimeout(tryInit, 100);
        } else {
            console.error('Libraries not loaded after', maxAttempts, 'attempts');
            console.log('jQuery:', typeof jQuery !== 'undefined', 'Chessboard:', typeof Chessboard !== 'undefined');
            showError('Chessboard library not loaded. Please refresh the page.');
        }
    };
    
    tryInit();
}

function updateBoard(fen) {
    // Update FEN display
    document.getElementById('currentFen').textContent = fen;

    // Extract just the position part (before the first space)
    const positionPart = fen.split(' ')[0];
    
    // Use global board instance or local board variable
    const boardInstance = board || window.chessBoardInstance;
    
    // Update chessboard position
    if (boardInstance && typeof boardInstance.position === 'function') {
        try {
            boardInstance.position(positionPart);
            console.log('Board updated with FEN:', positionPart);
        } catch (error) {
            console.error('Error updating board position:', error, 'FEN:', positionPart);
            showError('Invalid FEN position: ' + error.message);
        }
    } else {
        console.warn('Board instance not available, attempting to initialize...');
        // Try to initialize if not available
        if (typeof jQuery !== 'undefined' && typeof Chessboard !== 'undefined') {
            initializeBoard();
            // Try again after a short delay
            setTimeout(() => {
                const newInstance = board || window.chessBoardInstance;
                if (newInstance && typeof newInstance.position === 'function') {
                    newInstance.position(positionPart);
                }
            }, 200);
        } else {
            console.error('Libraries not loaded - jQuery:', typeof jQuery !== 'undefined', 'Chessboard:', typeof Chessboard !== 'undefined');
        }
    }
}

// Allow Enter key to connect
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('gameIdInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            connectToGame();
        }
    });
});


