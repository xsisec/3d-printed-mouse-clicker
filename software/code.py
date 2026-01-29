import network
import socket
from machine import Pin, PWM
import time
import _thread
import urandom  # MicroPython random module

# ---- Wi-Fi Setup ----
SSID = 'trojan'
PASSWORD = 'DanielElmnas'

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(SSID, PASSWORD)
print("Connecting to WiFi...", end='')
while not wifi.isconnected():
    time.sleep(1)
    print(".", end='')
print("\nConnected! IP:", wifi.ifconfig()[0])

# ---- Servo Setup ----
servo = PWM(Pin(2), freq=50)

# ---- Global Variables ----
current_angle = 90        # Start at middle
running = False           # Flag for manual spin
loop_mode = False         # Flag for loop mode
calibrated_angle = 90     # Reference for loop
spin_direction = 1        # 1 = forward, -1 = reverse
min_delay_ms = 1000       # Minimum random delay in ms
max_delay_ms = 5000       # Maximum random delay in ms

# ---- Servo Control ----
def set_angle(angle):
    global current_angle
    if angle < 0: angle = 0
    if angle > 180: angle = 180
    min_duty = 1638   # 0.5ms
    max_duty = 8192   # 2.5ms
    duty = int(min_duty + (max_duty - min_duty) * angle / 180)
    servo.duty_u16(duty)
    current_angle = angle

# ---- Manual Spin Thread ----
def manual_spin(speed=100):
    global running, spin_direction
    running = True
    while running and not loop_mode:
        set_angle(current_angle + spin_direction)
        time.sleep_ms(speed)

# ---- Loop Thread with Random Delay ----
def loop_press(retract=15, speed=50):
    global running, loop_mode, calibrated_angle, min_delay_ms, max_delay_ms
    loop_mode = True
    running = True
    while running and loop_mode:
        # Move back
        for angle in range(calibrated_angle, calibrated_angle - retract - 1, -1):
            set_angle(angle)
            time.sleep_ms(speed)
        # Move forward
        for angle in range(calibrated_angle - retract, calibrated_angle + retract + 1):
            set_angle(angle)
            time.sleep_ms(speed)
        # Random delay before next loop
        delay = urandom.getrandbits(16) % (max_delay_ms - min_delay_ms + 1) + min_delay_ms
        time.sleep_ms(delay)
    loop_mode = False

# ---- Web Page ----
html = """<!DOCTYPE html>
<html>
<head><title>Servo Blade Control</title></head>
<body>
<h1>Servo Blade Control</h1>

<h3>Manual Spin</h3>
<form>
<input type="submit" name="spin_forward" value="Spin Forward">
<input type="submit" name="spin_reverse" value="Spin Reverse">
<input type="submit" name="stop_spin" value="Stop">
</form>

<h3>Calibration</h3>
<form>
<input type="submit" name="calibrate" value="Calibrate Startpoint">
</form>

<h3>Loop Mode</h3>
<form>
Press/release retract (degrees): <input type="number" name="retract" value="15"><br>
Speed (ms per step): <input type="number" name="speed" value="50"><br>
Random delay min (ms): <input type="number" name="min_delay" value="1000"><br>
Random delay max (ms): <input type="number" name="max_delay" value="5000"><br>
<input type="submit" name="start_loop" value="Start Loop">
<input type="submit" name="stop_loop" value="Stop Loop">
</form>

<p>{status}</p>
</body>
</html>
"""

# ---- Web Server ----
def start_server():
    global running, spin_direction, calibrated_angle, loop_mode
    global min_delay_ms, max_delay_ms

    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    print("Listening on", addr)

    status = "Idle"

    while True:
        cl, addr = s.accept()
        request = cl.recv(1024).decode()
        print("Request:", request)

        try:
            if 'GET /?' in request:
                params = request.split('GET /?')[1].split(' ')[0]
                param_dict = {}
                for pair in params.split('&'):
                    if '=' in pair:
                        k, v = pair.split('=')
                        param_dict[k] = v

                # Manual spin controls
                if 'spin_forward' in param_dict:
                    if not running:
                        spin_direction = 1
                        _thread.start_new_thread(manual_spin, ())
                    status = "Spinning Forward"
                elif 'spin_reverse' in param_dict:
                    if not running:
                        spin_direction = -1
                        _thread.start_new_thread(manual_spin, ())
                    status = "Spinning Reverse"
                elif 'stop_spin' in param_dict:
                    running = False
                    status = "Manual Spin Stopped"

                # Calibration
                elif 'calibrate' in param_dict:
                    calibrated_angle = current_angle
                    status = f"Calibrated at {calibrated_angle}°"

                # Loop mode
                elif 'start_loop' in param_dict:
                    retract = int(param_dict.get('retract', 15))
                    speed = int(param_dict.get('speed', 50))
                    min_delay_ms = int(param_dict.get('min_delay', 1000))
                    max_delay_ms = int(param_dict.get('max_delay', 5000))
                    if not loop_mode:
                        _thread.start_new_thread(loop_press, (retract, speed))
                    status = f"Loop Mode Started (retract {retract}°, speed {speed}ms/step, delay {min_delay_ms}-{max_delay_ms}ms)"
                elif 'stop_loop' in param_dict:
                    running = False
                    loop_mode = False
                    status = "Loop Mode Stopped"

        except Exception as e:
            print("Error:", e)
            status = "Idle"

        response = html.format(status=status)
        cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        cl.send(response)
        cl.close()

# ---- Run Server ----
start_server()

