import asyncio
import json
import websockets
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

# ---------------------------
# Globals
# ---------------------------
connected = set()         # simulator clients
browser_clients = set()   # browser clients
async_loop = None
collision_count = 0

FLOOR_HALF = 50

def corner_to_coords(corner: str, margin=5):
    c = corner.upper()
    x = FLOOR_HALF - margin if "E" in c else -(FLOOR_HALF - margin)
    z = FLOOR_HALF - margin if ("S" in c or "B" in c) else -(FLOOR_HALF - margin)
    if c in ("NE", "EN", "TR"): x, z = (FLOOR_HALF - margin, -(FLOOR_HALF - margin))
    if c in ("NW", "WN", "TL"): x, z = (-(FLOOR_HALF - margin), -(FLOOR_HALF - margin))
    if c in ("SE", "ES", "BR"): x, z = (FLOOR_HALF - margin, (FLOOR_HALF - margin))
    if c in ("SW", "WS", "BL"): x, z = (-(FLOOR_HALF - margin), (FLOOR_HALF - margin))
    return {"x": x, "y": 0, "z": z}

# ---------------------------
# WebSocket Handler (Simulator)
# ---------------------------
async def ws_handler(websocket, path=None):
    global collision_count
    print("[SIM] Simulator connected via WebSocket")
    connected.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print("[SIM] Received:", data)

                # Track collision count
                if isinstance(data, dict) and data.get("type") == "collision" and data.get("collision"):
                    collision_count += 1
                    print(f"[SIM] Collision! Total: {collision_count}")

                # Broadcast position updates (and all other messages)
                await broadcast_to_browsers(data)

            except Exception as e:
                print("[SIM] Failed to process message:", e)
    except websockets.exceptions.ConnectionClosed:
        print("[SIM] Simulator disconnected")
    finally:
        connected.remove(websocket)

# ---------------------------
# WebSocket Handler (Browser)
# ---------------------------
async def browser_ws_handler(websocket, path=None):
    print("[WEB] Browser connected via WebSocket")
    browser_clients.add(websocket)
    try:
        async for message in websocket:
            print("[WEB] Received from browser:", message)
    except websockets.exceptions.ConnectionClosed:
        print("[WEB] Browser disconnected")
    finally:
        browser_clients.remove(websocket)

# ---------------------------
# Broadcasts
# ---------------------------
def broadcast(msg: dict):
    if not connected and not browser_clients:
        return False
    msg_json = json.dumps(msg)

    # Send to simulator clients
    for ws in list(connected):
        asyncio.run_coroutine_threadsafe(ws.send(msg_json), async_loop)

    # Send to browser clients
    for ws in list(browser_clients):
        asyncio.run_coroutine_threadsafe(ws.send(msg_json), async_loop)

    return True

async def broadcast_to_browsers(msg: dict):
    if not browser_clients:
        return
    msg_json = json.dumps(msg)
    for ws in list(browser_clients):
        try:
            await ws.send(msg_json)
        except Exception as e:
            print("[WEB] Failed to send to browser:", e)

# ---------------------------
# Flask API Endpoints
# ---------------------------
@app.route('/move', methods=['POST'])
def move():
    data = request.get_json()
    if not data or 'x' not in data or 'z' not in data:
        return jsonify({'error': 'Missing x or z'}), 400
    msg = {"command": "move", "target": {"x": data['x'], "y": 0, "z": data['z']}}
    broadcast(msg)
    return jsonify({'status': 'move command sent', 'command': msg})

@app.route('/move_rel', methods=['POST'])
def move_rel():
    data = request.get_json()
    if 'turn' not in data or 'distance' not in data:
        return jsonify({'error': 'Missing turn or distance'}), 400
    msg = {"command": "move_relative", "turn": data['turn'], "distance": data['distance']}
    broadcast(msg)
    return jsonify({'status': 'move relative command sent', 'command': msg})

@app.route('/stop', methods=['POST'])
def stop():
    msg = {"command": "stop"}
    broadcast(msg)
    return jsonify({'status': 'stop command sent'})

@app.route('/capture', methods=['POST'])
def capture():
    msg = {"command": "capture_image"}
    broadcast(msg)
    return jsonify({'status': 'capture command sent'})

@app.route('/goal', methods=['POST'])
def set_goal():
    data = request.get_json() or {}
    if 'corner' in data:
        pos = corner_to_coords(str(data['corner']))
    elif 'x' in data and 'z' in data:
        pos = {"x": float(data['x']), "y": float(data.get('y', 0)), "z": float(data['z'])}
    else:
        return jsonify({'error': 'Invalid goal'}), 400
    msg = {"command": "set_goal", "position": pos}
    broadcast(msg)
    return jsonify({'status': 'goal set', 'goal': pos})

@app.route('/obstacles/positions', methods=['POST'])
def set_obstacle_positions():
    data = request.get_json() or {}
    positions = data.get('positions')
    if not isinstance(positions, list):
        return jsonify({'error': 'Invalid positions'}), 400
    norm = [{"x": float(p['x']), "y": float(p.get('y', 2)), "z": float(p['z'])} for p in positions]
    msg = {"command": "set_obstacles", "positions": norm}
    broadcast(msg)
    return jsonify({'status': 'obstacles updated', 'count': len(norm)})

@app.route('/obstacles/motion', methods=['POST'])
def set_obstacle_motion():
    data = request.get_json() or {}
    if 'enabled' not in data:
        return jsonify({'error': 'Missing "enabled"'}), 400
    msg = {
        "command": "set_obstacle_motion",
        "enabled": bool(data['enabled']),
        "speed": float(data.get('speed', 0.05)),
        "velocities": data.get('velocities'),
        "bounds": data.get('bounds', {"minX": -45, "maxX": 45, "minZ": -45, "maxZ": 45}),
        "bounce": bool(data.get('bounce', True)),
    }
    broadcast(msg)
    return jsonify({'status': 'obstacle motion updated'})

@app.route('/collisions', methods=['GET'])
def get_collisions():
    return jsonify({'count': collision_count})

@app.route('/reset', methods=['POST'])
def reset():
    global collision_count
    collision_count = 0
    msg = {"command": "reset"}
    broadcast(msg)
    return jsonify({'status': 'reset broadcast', 'collisions': collision_count})

# ---------------------------
# Flask + WebSocket Startup
# ---------------------------
def start_flask():
    app.run(port=5000)

async def main():
    global async_loop
    async_loop = asyncio.get_running_loop()

    # WebSocket server for simulator
    sim_server = await websockets.serve(ws_handler, "localhost", 8080)
    print("WebSocket for simulator: ws://localhost:8080")

    # WebSocket server for browser
    browser_server = await websockets.serve(browser_ws_handler, "localhost", 8765)
    print("WebSocket for browser: ws://localhost:8765")

    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    asyncio.run(main())