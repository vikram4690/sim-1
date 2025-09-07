import asyncio
import websockets
import requests
import json
import base64
import cv2
import numpy as np
import threading
import time
import random
from typing import Optional, Tuple

# ------------------------
# Configuration
# ------------------------
BASE_URL = "http://127.0.0.1:5000"
CAPTURE_URL = f"{BASE_URL}/capture"
MOVE_URL = f"{BASE_URL}/move_rel"
COLLISION_URL = f"{BASE_URL}/collisions"
RESET_URL = f"{BASE_URL}/reset"
GOAL_URL = f"{BASE_URL}/goal"
WS_URL = "ws://localhost:8080"

# ------------------------
# Global State
# ------------------------
class RobotState:
    def __init__(self):
        self.latest_frame = None
        self.goal_reached = False
        self.collision_count = 0
        self.ws_connected = False
        self.vision_working = False
        self.current_direction = 0
        self.last_collision_count = 0
        self.stuck_counter = 0

robot_state = RobotState()

# ------------------------
# HTTP API Functions
# ------------------------
def move_robot(turn: float, distance: float) -> bool:
    """Send movement command to robot"""
    payload = {"turn": turn, "distance": distance}
    try:
        resp = requests.post(MOVE_URL, json=payload, timeout=5)
        if resp.status_code == 200:
            print(f"Move: turn={turn}°, distance={distance}")
            robot_state.current_direction = (robot_state.current_direction + turn) % 360
            return True
        else:
            print(f"Move failed: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"Move error: {e}")
        return False

def trigger_capture() -> bool:
    """Request image capture from robot camera"""
    try:
        resp = requests.post(CAPTURE_URL, timeout=3)
        return resp.status_code == 200
    except Exception as e:
        print(f"Capture error: {e}")
        return False

def reset_simulator() -> bool:
    """Reset simulator state"""
    try:
        resp = requests.post(RESET_URL, timeout=5)
        if resp.status_code == 200:
            robot_state.collision_count = 0
            robot_state.last_collision_count = 0
            robot_state.stuck_counter = 0
            robot_state.current_direction = 0
            robot_state.goal_reached = False
            print("Simulator reset")
            return True
    except Exception as e:
        print(f"Reset error: {e}")
    return False

def set_goal(corner: str) -> bool:
    """Set goal position"""
    payload = {"corner": corner}
    try:
        resp = requests.post(GOAL_URL, json=payload, timeout=5)
        if resp.status_code == 200:
            print(f"Goal set to {corner}")
            return True
    except Exception as e:
        print(f"Goal set error: {e}")
    return False

def get_collision_count() -> int:
    """Get current collision count from server"""
    try:
        resp = requests.get(COLLISION_URL, timeout=3)
        if resp.status_code == 200:
            return resp.json().get("count", 0)
    except Exception as e:
        print(f"Collision count error: {e}")
    return robot_state.collision_count

# ------------------------
# WebSocket Handler
# ------------------------
async def websocket_handler():
    """Handle WebSocket communication with simulator"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"Connecting to WebSocket (attempt {retry_count + 1})...")
            async with websockets.connect(WS_URL) as ws:
                robot_state.ws_connected = True
                print("WebSocket connected")
                
                # Test vision system
                await test_vision_system(ws)
                
                async for message in ws:
                    await process_websocket_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket disconnected")
        except Exception as e:
            print(f"WebSocket error: {e}")
        
        robot_state.ws_connected = False
        retry_count += 1
        if retry_count < max_retries:
            await asyncio.sleep(2)
    
    print("WebSocket connection failed after all retries")

async def test_vision_system(ws):
    """Test if computer vision system is working"""
    print("Testing vision system...")
    robot_state.latest_frame = None
    
    # Send capture command
    if trigger_capture():
        # Wait for image response
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
            await process_websocket_message(message)
            if robot_state.latest_frame is not None:
                robot_state.vision_working = True
                print("Vision system: WORKING")
            else:
                print("Vision system: NOT WORKING - using fallback navigation")
        except asyncio.TimeoutError:
            print("Vision system: TIMEOUT - using fallback navigation")
    else:
        print("Vision system: CAPTURE FAILED - using fallback navigation")

async def process_websocket_message(message: str):
    """Process incoming WebSocket message"""
    try:
        data = json.loads(message)
        message_type = data.get("type", "unknown")
        
        if message_type == "capture_image_response":
            await handle_image_response(data)
        elif message_type == "collision":
            robot_state.collision_count += 1
            print(f"Collision detected! Total: {robot_state.collision_count}")
        elif message_type == "goal_reached":
            robot_state.goal_reached = True
            print("GOAL REACHED!")
        elif message_type == "confirmation":
            pass  # Movement confirmations
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
    except Exception as e:
        print(f"Message processing error: {e}")

async def handle_image_response(data: dict):
    """Process captured image from robot camera"""
    try:
        if "image" not in data:
            return
        
        # Decode base64 image
        b64_str = data["image"].split(",")[1]
        img_bytes = base64.b64decode(b64_str)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if frame is not None:
            robot_state.latest_frame = frame
            robot_state.vision_working = True
            # Display image for debugging
            cv2.imshow("Robot Camera", frame)
            cv2.waitKey(1)
        
    except Exception as e:
        print(f"Image processing error: {e}")

# ------------------------
# Computer Vision
# ------------------------
def detect_obstacle(img: np.ndarray) -> bool:
    """Detect obstacles using computer vision"""
    if img is None:
        return False
    
    try:
        # Convert to HSV for better color detection
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Green color range for obstacles (adjust based on your obstacles)
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([85, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        # Focus on the path ahead (bottom center of image)
        h, w = mask.shape
        roi_height = int(h * 0.4)  # Bottom 40% of image
        roi_width = int(w * 0.6)   # Center 60% of image
        roi_x = (w - roi_width) // 2
        roi_y = h - roi_height
        
        roi = mask[roi_y:h, roi_x:roi_x + roi_width]
        obstacle_pixels = cv2.countNonZero(roi)
        
        # Threshold for obstacle detection
        threshold = 300
        is_obstacle = obstacle_pixels > threshold
        
        if is_obstacle:
            print(f"Obstacle detected! Pixels: {obstacle_pixels}")
        
        return is_obstacle
        
    except Exception as e:
        print(f"Vision error: {e}")
        return False

def get_best_direction(img: np.ndarray) -> float:
    """Analyze image to find best direction to move"""
    if img is None:
        return 0
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([85, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        h, w = mask.shape
        
        # Divide bottom half into left, center, right sections
        sections = {
            'left': mask[h//2:h, 0:w//3],
            'center': mask[h//2:h, w//3:2*w//3],
            'right': mask[h//2:h, 2*w//3:w]
        }
        
        # Count obstacles in each section
        obstacle_counts = {
            section: cv2.countNonZero(area) 
            for section, area in sections.items()
        }
        
        # Find clearest path
        min_obstacles = min(obstacle_counts.values())
        clear_sections = [section for section, count in obstacle_counts.items() 
                         if count == min_obstacles]
        
        # Prefer center, then right, then left
        if 'center' in clear_sections:
            return 0  # Go straight
        elif 'right' in clear_sections:
            return -30  # Turn right
        elif 'left' in clear_sections:
            return 30   # Turn left
        else:
            return 45   # Turn more if all blocked
            
    except Exception as e:
        print(f"Direction analysis error: {e}")
        return 0

# ------------------------
# Navigation Strategies
# ------------------------
def vision_based_navigation(corner: str) -> int:
    """Navigate using computer vision"""
    print(f"Using VISION-BASED navigation to {corner}")
    
    steps = 0
    max_steps = 100
    no_image_count = 0
    
    while not robot_state.goal_reached and steps < max_steps:
        steps += 1
        print(f"\nVision Step {steps}")
        
        # Capture image
        robot_state.latest_frame = None
        if trigger_capture():
            # Wait for image
            wait_time = 0
            while robot_state.latest_frame is None and wait_time < 2:
                time.sleep(0.1)
                wait_time += 0.1
            
            if robot_state.latest_frame is not None:
                no_image_count = 0
                
                # Analyze image
                if detect_obstacle(robot_state.latest_frame):
                    # Obstacle detected - find best direction
                    turn_angle = get_best_direction(robot_state.latest_frame)
                    print(f"Obstacle ahead - turning {turn_angle}°")
                    move_robot(turn_angle, 0)
                    time.sleep(0.5)
                    # Move forward after turning
                    move_robot(0, 2)
                else:
                    # Path clear - move forward
                    print("Path clear - moving forward")
                    move_robot(0, 3)
            else:
                no_image_count += 1
                print(f"No image received ({no_image_count})")
                if no_image_count > 3:
                    print("Switching to fallback navigation")
                    return fallback_navigation(corner, steps)
                # Move cautiously without vision
                move_robot(0, 1)
        else:
            print("Capture failed - moving cautiously")
            move_robot(0, 1)
        
        time.sleep(1)
        
        # Check progress
        if steps % 10 == 0:
            collisions = get_collision_count()
            print(f"Progress: {steps} steps, {collisions} collisions")
    
    return get_collision_count()

def fallback_navigation(corner: str, start_steps: int = 0) -> int:
    """Navigate without computer vision using collision-based feedback"""
    print(f"Using FALLBACK navigation to {corner}")
    
    # Corner direction mapping
    corner_directions = {
        "NE": 45, "NW": 315, "SE": 135, "SW": 225
    }
    
    target_direction = corner_directions.get(corner, 45)
    
    # Align toward goal
    direction_diff = target_direction - robot_state.current_direction
    if direction_diff > 180:
        direction_diff -= 360
    elif direction_diff < -180:
        direction_diff += 360
    
    if abs(direction_diff) > 15:
        print(f"Aligning toward goal: turning {direction_diff}°")
        move_robot(direction_diff, 0)
        time.sleep(0.5)
    
    steps = start_steps
    max_steps = 80
    
    while not robot_state.goal_reached and steps < max_steps:
        steps += 1
        print(f"\nFallback Step {steps}")
        
        current_collisions = get_collision_count()
        collision_happened = current_collisions > robot_state.last_collision_count
        
        if collision_happened:
            robot_state.stuck_counter += 1
            print(f"Collision detected! (Total: {current_collisions})")
            
            # Avoid obstacle
            if robot_state.stuck_counter < 3:
                turn_angle = random.choice([45, 60, -45, -60])
            else:
                turn_angle = random.choice([90, -90, 120, -120])
            
            print(f"Avoiding obstacle: turning {turn_angle}°")
            move_robot(turn_angle, 0)
            time.sleep(0.5)
            move_robot(0, 1.5)  # Small forward move
            
        else:
            robot_state.stuck_counter = max(0, robot_state.stuck_counter - 1)
            
            # Periodically correct direction toward goal
            if steps % 7 == 0:
                current_dir_diff = target_direction - robot_state.current_direction
                if current_dir_diff > 180:
                    current_dir_diff -= 360
                elif current_dir_diff < -180:
                    current_dir_diff += 360
                
                if abs(current_dir_diff) > 20:
                    correction = current_dir_diff * 0.4
                    print(f"Course correction: {correction:.1f}°")
                    move_robot(correction, 0)
                    time.sleep(0.3)
            
            # Move forward
            move_robot(0, 2.5)
        
        robot_state.last_collision_count = current_collisions
        time.sleep(0.8)
    
    return get_collision_count()

# ------------------------
# Main Navigation Function
# ------------------------
def navigate_to_goal(corner: str) -> int:
    """Main navigation function - uses vision if available, fallback otherwise"""
    print(f"\n=== Navigating to {corner} corner ===")
    
    # Setup
    reset_simulator()
    time.sleep(1)
    set_goal(corner)
    time.sleep(1)
    
    # Choose navigation strategy
    if robot_state.vision_working and robot_state.ws_connected:
        final_collisions = vision_based_navigation(corner)
    else:
        final_collisions = fallback_navigation(corner)
    
    # Results
    if robot_state.goal_reached:
        print(f"SUCCESS! Reached {corner} with {final_collisions} collisions")
    else:
        print(f"TIMEOUT! Failed to reach {corner}. Collisions: {final_collisions}")
    
    return final_collisions

# ------------------------
# WebSocket Thread Management
# ------------------------
def start_websocket_thread():
    """Start WebSocket handler in background thread"""
    def run_websocket():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(websocket_handler())
    
    thread = threading.Thread(target=run_websocket, daemon=True)
    thread.start()
    return thread

# ------------------------
# Main Execution
# ------------------------
def main():
    print("Autonomous Robot Controller")
    print("=" * 50)
    
    # Start WebSocket connection
    ws_thread = start_websocket_thread()
    
    # Wait for connection
    connection_timeout = 10
    wait_time = 0
    while not robot_state.ws_connected and wait_time < connection_timeout:
        print("Waiting for WebSocket connection...")
        time.sleep(1)
        wait_time += 1
    
    if robot_state.ws_connected:
        print("WebSocket connected successfully")
    else:
        print("WebSocket connection failed - using HTTP-only mode")
    
    # Additional setup time
    time.sleep(2)
    
    # Test corners
    corners = ["NE", "NW", "SE", "SW"]
    results = []
    
    for i, corner in enumerate(corners):
        print(f"\n{'='*20} RUN {i+1}/{len(corners)} {'='*20}")
        
        try:
            collisions = navigate_to_goal(corner)
            results.append(collisions)
        except KeyboardInterrupt:
            print("\nStopped by user")
            break
        except Exception as e:
            print(f"Error in run {i+1}: {e}")
            results.append(-1)
        
        # Wait between runs
        if i < len(corners) - 1:
            print("Waiting before next run...")
            time.sleep(3)
    
    # Final Results
    print(f"\n{'='*50}")
    print("FINAL RESULTS")
    print(f"{'='*50}")
    
    valid_results = [r for r in results if r >= 0]
    
    for i, corner in enumerate(corners[:len(results)]):
        if i < len(results):
            if results[i] >= 0:
                print(f"{corner}: {results[i]} collisions")
            else:
                print(f"{corner}: FAILED")
    
    if valid_results:
        avg_collisions = sum(valid_results) / len(valid_results)
        print(f"\nAverage collisions: {avg_collisions:.1f}")
        print(f"Vision system used: {'YES' if robot_state.vision_working else 'NO (fallback used)'}")
    
    cv2.destroyAllWindows()
    print("\nNavigation test completed!")

if __name__ == "__main__":
    main()