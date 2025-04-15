import asyncio
import json
import websockets
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

# Global variables to store connected WebSocket clients and the asyncio loop
connected = set()
async_loop = None

# ---------------------------
# WebSocket Handler
# ---------------------------
async def ws_handler(websocket, path=None):
    print("Client connected via WebSocket")
    connected.add(websocket)
    try:
        async for message in websocket:
            print("Received from simulator:", message)
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected.remove(websocket)

# ---------------------------
# Flask API Endpoints
# ---------------------------
@app.route('/move', methods=['POST'])
def move():
    data = request.get_json()
    if not data or 'x' not in data or 'z' not in data:
         return jsonify({'error': 'Missing parameters. Please provide "x" and "z".'}), 400
    x = data['x']
    z = data['z']
    msg = {"command": "move", "target": {"x": x, "y": 0, "z": z}}
    if not connected:
         return jsonify({'error': 'No connected simulators.'}), 400
    # Send the move command to all connected clients
    for ws in list(connected):
         asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
    return jsonify({'status': 'move command sent', 'command': msg})

@app.route('/move_rel', methods=['POST'])
def move_rel():
    data = request.get_json()
    if not data or 'turn' not in data or 'distance' not in data:
         return jsonify({'error': 'Missing parameters. Please provide "turn" and "distance".'}), 400
    turn = data['turn']
    distance = data['distance']
    msg = {"command": "move_relative", "turn": turn, "distance": distance}
    if not connected:
         return jsonify({'error': 'No connected simulators.'}), 400
    for ws in list(connected):
         asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
    return jsonify({'status': 'move relative command sent', 'command': msg})

@app.route('/stop', methods=['POST'])
def stop():
    msg = {"command": "stop"}
    if not connected:
         return jsonify({'error': 'No connected simulators.'}), 400
    for ws in list(connected):
         asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
    return jsonify({'status': 'stop command sent', 'command': msg})

@app.route('/capture', methods=['POST'])
def capture():
    msg = {"command": "capture_image"}
    if not connected:
         return jsonify({'error': 'No connected simulators.'}), 400
    for ws in list(connected):
         asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
    return jsonify({'status': 'capture command sent', 'command': msg})

# ---------------------------
# Flask Server Thread Starter
# ---------------------------
def start_flask():
    # Start Flask on port 5000
    app.run(port=5000)

# ---------------------------
# Main Async Function for WebSocket Server
# ---------------------------
async def main():
    global async_loop
    async_loop = asyncio.get_running_loop()
    # Start the WebSocket server on ws://localhost:8080
    ws_server = await websockets.serve(ws_handler, "localhost", 8080)
    print("WebSocket server started on ws://localhost:8080")
    # Keep the WebSocket server running
    await ws_server.wait_closed()

# ---------------------------
# Entry Point
# ---------------------------
if __name__ == "__main__":
    # Start the Flask API in a separate thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run the WebSocket server in the main asyncio event loop
    asyncio.run(main())
