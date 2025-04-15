# Robot Simulator Project
## Overview
This project integrates a Three.js-based robot simulator with a Python WebSocket server and Flask API endpoints. The simulator supports both absolute and relative movement commands, while collision detection is handled on the client side (in the Three.js code).


## Prerequisites
- **Python 3.7+**
- **pip** (Python package installer)
- A modern web browser (e.g., Chrome, Firefox) to run the Three.js simulator
- (Optional) An HTTP client (e.g., curl, Postman) for testing the Flask API endpoints

## Required Python Packages
Install the following packages using pip:
```bash
pip install websockets flask
```

## Setup and Running the Project 
- git clone git@github.com:terafac/sim-1.git
- cd sim-1
- Install Dependencies: Open a terminal in the project directory and run:
```bash
pip install websockets flask
``` 
- Run the Python Server:
- In the terminal, navigate to the project directory.

- Start the server by running:
```bash
python server.py
```
The server will start:

A WebSocket server on ws://localhost:8080

A Flask API on port 5000

Open the Three.js Simulator:

Open the index.html file in your web browser.

To run from terminal on port 8000, you can use the command

```bash
python -m http.server
```

The simulator will automatically connect to the WebSocket server at ws://localhost:8080.

Check your browser’s console or the server terminal for connection messages (e.g., "Client connected via WebSocket").

# API Endpoints and Simulator Responses

You can control the robot by sending HTTP POST requests to the Flask API endpoints.

---

## 1. Absolute Movement

- **Endpoint:** `/move`
- **Method:** `POST`

### Payload Example:
```json
{
  "x": 10,
  "z": -5
}

```
## Curl Example:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"x": 10, "z": -5}' http://localhost:5000/move
```
## 2. Relative Movement


- **Endpoint:** `/move_rel`
- **Method:** `POST`

### Payload Example:
```json
{
  "turn": 45,
  "distance": 10
}

```
## Curl Example:
```bash 
curl -X POST -H "Content-Type: application/json" -d '{"turn": 45, "distance": 10}' http://localhost:5000/move_rel
```

## 3.Stop Command


- **Endpoint:** `/stop`
- **Method:** `POST`

## Curl Example:
```bash 
curl -X POST http://localhost:5000/stop
```
## 4. Capture Image


- **Endpoint:** `/capture`
- **Method:** `POST`

## Curl Example 
```bask 
curl -X POST http://localhost:5000/capture
```

# Simulator Responses
The Three.js simulator sends back WebSocket messages. Examples include:

## 1. Absolute Move Confirmation:
```bask 
{
  "type": "confirmation",
  "message": "Move command received",
  "target": { "x": 10, "y": 0, "z": -5 }
}
```
## 2. Relative Move Confirmation:
```bash
{
  "type": "confirmation",
  "message": "Relative move command executed",
  "target": { "angle": 45, "distance": 10 }
}
```
## 3. Collision Notification
```bash
{
  "type": "collision",
  "collision": true,
  "position": { "x": <current_x>, "y": <current_y>, "z": <current_z> },
  "obstacle": { "position": { "x": <obs_x>, "y": <obs_y>, "z": <obs_z> } }
}
```

## 4. Capture Image Response:
```bash 
{
  "type": "capture_image_response",
  "image": "<Base64 encoded PNG image>",
  "timestamp": <timestamp>,
  "position": { "x": <current_x>, "y": <current_y>, "z": <current_z> }
}
```
#Additional Information

## Collision Detection
The Three.js simulator continuously checks for collisions between the robot and obstacles. When a collision is detected, the simulator stops the robot and sends a collision message via WebSocket.

## Flask & WebSocket Integration
The Flask API (running on port 5000) communicates with the WebSocket server (running on port 8080) via shared global state and the asyncio event loop.

## Troubleshooting
Port Availability: Ensure that ports 5000 and 8080 are free.

Browser Console: Check for errors if the simulator does not load or connect.

Firewall/Antivirus: Verify that your firewall or antivirus software is not blocking the connections.
