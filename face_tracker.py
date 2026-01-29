import cv2
import mediapipe as mp
import time
import requests
from collections import deque

# ================= NODE SERVER =================
SERVER_URL = "https://mood-relay-server.onrender.com/update-angle"

# ================= MEDIAPIPE =================
mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(min_detection_confidence=0.7)

# ================= CAMERA =================
cap = cv2.VideoCapture(1)   # External webcam
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# ================= SERVO =================
SERVO_MIN = 0
SERVO_MAX = 180
CENTER_ANGLE = 90
servo_angle = CENTER_ANGLE
last_sent_angle = CENTER_ANGLE

# ================= STABILITY PARAMETERS =================
FACE_HISTORY = deque(maxlen=7)
DEAD_ZONE = 0.20
ANGLE_STEP_LIMIT = 0.6
SEND_THRESHOLD = 1.5

# ================= NO-FACE HANDLING =================
NO_FACE_TIMEOUT = 1.2
CENTER_RETURN_SPEED = 0.4
last_face_time = time.time()

# ================= SEND CONTROL =================
SEND_INTERVAL = 0.10   # seconds
last_send_time = 0

NO_FACE_SEND_INTERVAL = 1.0
last_no_face_send = 0

print("Face tracker running (HEADLESS MODE)")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)

    small = cv2.resize(frame, (320, 240))
    h, w, _ = small.shape
    center_x = w / 2

    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    results = face_detection.process(rgb)

    face_detected = False

    if results.detections:
        face_detected = True
        last_face_time = time.time()

        bbox = results.detections[0].location_data.relative_bounding_box
        face_x = (bbox.xmin + bbox.width / 2) * w

        error = (face_x - center_x) / center_x
        if abs(error) < DEAD_ZONE:
            error = 0

        FACE_HISTORY.append(error)
        avg_error = sum(FACE_HISTORY) / len(FACE_HISTORY)

        target = servo_angle + avg_error * 15
        target = max(SERVO_MIN, min(SERVO_MAX, target))

        delta = target - servo_angle
        delta = max(-ANGLE_STEP_LIMIT, min(ANGLE_STEP_LIMIT, delta))
        servo_angle += delta

    else:
        if time.time() - last_face_time > NO_FACE_TIMEOUT:
            if abs(servo_angle - CENTER_ANGLE) > CENTER_RETURN_SPEED:
                servo_angle += CENTER_RETURN_SPEED if servo_angle < CENTER_ANGLE else -CENTER_RETURN_SPEED

    # ================= SEND TO SERVER =================
    now = time.time()

    # --- FACE DETECTED ---
    if face_detected:
        if abs(servo_angle - last_sent_angle) >= SEND_THRESHOLD and (now - last_send_time) > SEND_INTERVAL:
            try:
                requests.post(SERVER_URL, json={"angle": int(servo_angle)}, timeout=1.5)
                last_sent_angle = servo_angle
                last_send_time = now
            except:
                pass

    # --- NO FACE → SEND CENTER ---
    else:
        if (now - last_no_face_send) > NO_FACE_SEND_INTERVAL:
            try:
                requests.post(SERVER_URL, json={"angle": CENTER_ANGLE}, timeout=1.5)
                last_no_face_send = now
            except:
                pass


# ================= CLEANUP =================
cap.release()
