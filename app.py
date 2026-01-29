import json
import subprocess
import atexit
import os
import sys, time, threading, math, cv2, os, secrets, base64, hashlib, webbrowser, socket
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests, pyperclip
from deepface import DeepFace
from datetime import datetime
from collections import deque
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize

# PyQt5 UI
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QMessageBox,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QDialog, QListWidget, QListWidgetItem, QInputDialog
)
from PyQt5.QtGui import QConicalGradient

# Matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

# Optional serial
try:
    import serial
    SERIAL_AVAILABLE = True
except:
    SERIAL_AVAILABLE = False

# ---------- CONFIG ----------
FRAME_INTERVAL = 15.0
WEBCAM_INDEX = 0
SERIAL_PORT = "COM5"
SERIAL_BAUDRATE = 9600

face_tracker_process = None

# Node.js server configuration
NODE_SERVER_URL = "https://mood-relay-server.onrender.com"
WIFI_ENABLED = True

ESP32_IP = None

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or "5bf822e0f7e840d9a7388f8e8c6d7cec"
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SPOTIFY_AUTH_PORT = 8888
SPOTIFY_SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing"

# Playlist URIs for moods (update with your own Spotify playlist URIs)
PLAYLIST_FILE = "playlists.json"

MOODS = ["HAPPY", "NEUTRAL", "SAD", "ANGRY"]

EMOTION_SMOOTHING_WINDOW = 5
emotion_buffer = deque(maxlen=EMOTION_SMOOTHING_WINDOW)


def load_playlists():
    if not os.path.exists(PLAYLIST_FILE):
        with open(PLAYLIST_FILE, "w") as f:
            json.dump({m: None for m in MOODS}, f, indent=2)
    with open(PLAYLIST_FILE, "r") as f:
        return json.load(f)

def save_playlists(data):
    with open(PLAYLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)

PLAYLISTS = load_playlists()

# --------------------------
running = False
cam = None
ser = None
current_mood = "UNKNOWN"
current_score = 0
display_score = 0
history = []
log_lines = []

spotify_playing = False
spotify_playing_lock = threading.Lock()

def append_log(text):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"[{ts}] {text}")
    if len(log_lines) > 500:
        log_lines[:] = log_lines[-500:]

def preprocess_face(face_img):
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

def discover_esp32():
    global ESP32_IP
    try:
        ESP32_IP = socket.gethostbyname("robot-eyes.local")
        append_log(f"[mDNS] ESP32 found at {ESP32_IP}")
        return True
    except Exception as e:
        append_log(f"[mDNS] Resolve failed: {e}")
        return False

def start_face_tracker():
    global face_tracker_process

    if face_tracker_process is not None:
        return

    python_exe = sys.executable
    script_path = os.path.join(os.path.dirname(__file__), "face_tracker.py")

    face_tracker_process = subprocess.Popen(
        [python_exe, script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    append_log("[FaceTracker] Started background face tracker")


def stop_face_tracker():
    global face_tracker_process

    if face_tracker_process:
        try:
            face_tracker_process.terminate()
            face_tracker_process.wait(timeout=3)
        except Exception:
            face_tracker_process.kill()
        finally:
            face_tracker_process = None
            append_log("[FaceTracker] Stopped face tracker")


# ---------------- Spotify Controller ----------------
class SpotifyController:
    def __init__(self, client_id, redirect_uri, scopes):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0
        self.code_verifier = None
        self.code_challenge = None
        self.state = None
        self.logged_in = False
        self.lock = threading.Lock()

    def _generate_pkce_pair(self):
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).decode().rstrip("=")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.code_verifier = verifier
        self.code_challenge = challenge

    def build_authorize_url(self):
        self._generate_pkce_pair()
        self.state = secrets.token_urlsafe(16)
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": self.code_challenge,
            "state": self.state,
            "scope": self.scopes
        }
        return "https://accounts.spotify.com/authorize?" + urlencode(params)

    def start_local_server_and_listen(self, timeout=120):
        server = HTTPServer(("127.0.0.1", SPOTIFY_AUTH_PORT), self._make_handler_class())
        server.timeout = timeout
        append_log("[Spotify] Waiting for authorization callback ...")
        try:
            server.handle_request()
        except Exception as e:
            append_log(f"[Spotify] Local server error: {e}")

    def _make_handler_class(self):
        parent = self
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != urlparse(parent.redirect_uri).path:
                    self.send_response(404); self.end_headers(); return
                qs = parse_qs(parsed.query)
                code = qs.get("code", [None])[0]
                state = qs.get("state", [None])[0]
                if state != parent.state:
                    self.send_response(400); self.end_headers(); return
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Spotify authorized. Close this page.</h2></body></html>")
                parent.exchange_code_for_token(code)
            def log_message(self, *args): return
        return CallbackHandler

    def exchange_code_for_token(self, code):
        r = requests.post("https://accounts.spotify.com/api/token",
                          data={"grant_type":"authorization_code","code":code,
                                "redirect_uri":self.redirect_uri,"client_id":self.client_id,
                                "code_verifier":self.code_verifier},
                          headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=10)
        r.raise_for_status()
        token = r.json()
        with self.lock:
            self.access_token = token['access_token']
            self.refresh_token = token.get('refresh_token')
            self.token_expires_at = time.time() + token.get('expires_in',3600)-30
            self.logged_in = True
        append_log("[Spotify] Logged in, access token obtained")

    def refresh_access_token_if_needed(self):
        with self.lock:
            if not self.refresh_token or time.time() < self.token_expires_at-15: return
            r = requests.post("https://accounts.spotify.com/api/token",
                              data={"grant_type":"refresh_token","refresh_token":self.refresh_token,"client_id":self.client_id},
                              headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=10)
            if r.status_code == 200:
                token = r.json()
                self.access_token = token['access_token']
                self.token_expires_at = time.time() + token.get('expires_in',3600)-30
                append_log("[Spotify] Access token refreshed")

    def ensure_token_refresher(self):
        def loop():
            while True:
                try:
                    if self.logged_in: self.refresh_access_token_if_needed()
                    time.sleep(10)
                except: time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()

    def authorize_interactively(self):
        url = self.build_authorize_url()
        pyperclip.copy(url)
        append_log("[Spotify] URL copied to clipboard; opening browser ...")
        webbrowser.open(url)
        self.start_local_server_and_listen()
        if self.logged_in: self.ensure_token_refresher()

    def api_headers(self):
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"} if self.access_token else {}

    def _get_devices(self):
        try:
            r = requests.get("https://api.spotify.com/v1/me/player/devices", headers=self.api_headers(), timeout=10)
            return r.json().get("devices", [])
        except: return None

    def ensure_active_device(self):
        devices = self._get_devices()
        if not devices: return None
        for d in devices:
            if d.get("is_active"): return d.get("id")
        first = devices[0]
        try:
            r = requests.put("https://api.spotify.com/v1/me/player", headers=self.api_headers(),
                             json={"device_ids":[first.get("id")],"play":True}, timeout=10)
            return first.get("id") if r.status_code in (202,204) else None
        except: return None

    def get_playback_state(self):
        try:
            r = requests.get("https://api.spotify.com/v1/me/player", headers=self.api_headers(), timeout=10)
            return r.json() if r.status_code==200 else None
        except: return None

    def play_playlist_for_mood(self, mood):
        global spotify_playing, spotify_playing_lock
        if not self.logged_in: return False
        uri = PLAYLISTS.get(mood)
        if not uri: return False
        self.refresh_access_token_if_needed()
        device_id = self.ensure_active_device()
        url = f"https://api.spotify.com/v1/me/player/play?device_id={device_id}" if device_id else "https://api.spotify.com/v1/me/player/play"
        try:
            r = requests.put(url, headers=self.api_headers(), json={"context_uri": uri}, timeout=10)
            if r.status_code in (202,204):
                with spotify_playing_lock: spotify_playing = True
                append_log(f"[Spotify] Playing playlist for mood {mood}")
                return True
        except Exception as e: append_log(f"[Spotify] Exception play {mood}: {e}")
        return False

# ---------------- Mood mapping ----------------
def map_emotion_to_mood(emotion):
    if not emotion: return ("UNKNOWN",0)
    e = emotion.lower()
    if e=="happy": return ("HAPPY",100)
    if e=="neutral": return ("NEUTRAL",50)
    if e=="sad": return ("SAD",20)
    if e=="angry": return ("ANGRY",10)
    if e in ("fear","disgust"): return ("SAD",20)
    if e=="surprise": return ("NEUTRAL",50)
    if e=="contempt": return ("ANGRY",10)
    return ("UNKNOWN",0)

spotify_controller = None
_last_spotify_call_mood = None
_spotify_lock = threading.Lock()

def send_mood_via_serial(ser_conn, mood_text):
    try: ser_conn.write((mood_text+"\n").encode()); append_log(f"[Serial] Sent: {mood_text}")
    except Exception as e: append_log(f"[Serial] Send error: {e}")

def send_mood_via_wifi(mood_text, score):
    if not WIFI_ENABLED:
        return

    try:
        payload = {
            "mood": mood_text,
            "score": score,
            "timestamp": time.time()
        }

        requests.post(
            f"{NODE_SERVER_URL}/update-mood",
            json=payload,
            timeout=2
        )


        append_log(f"[WiFi] Sent mood to server: {mood_text}")

    except Exception as e:
        append_log(f"[WiFi] Server send error: {e}")

def detect_mood():
    global running, cam, ser, current_mood, current_score
    global spotify_controller, _last_spotify_call_mood, spotify_playing

    last_processed = 0

    while running:
        with spotify_playing_lock:
            if spotify_playing:
                time.sleep(2)
                continue

        ret, frame = cam.read()
        if not ret:
            time.sleep(0.2)
            continue

        now = time.time()
        if now - last_processed < FRAME_INTERVAL:
            time.sleep(0.1)
            continue

        last_processed = now

        try:
            # ---- FACE DETECTION + EMOTION ----
            analysis = DeepFace.analyze(
                img_path=frame,
                actions=['emotion'],
                detector_backend='retinaface',
                enforce_detection=True
            )

            if isinstance(analysis, list):
                analysis = analysis[0]

            emotion_scores = analysis.get("emotion", {})
            dominant = analysis.get("dominant_emotion", None)

            if not dominant:
                append_log("No dominant emotion detected")
                continue

            # ---- SMOOTH EMOTION ----
            emotion_buffer.append(emotion_scores)

            avg_scores = {}
            for scores in emotion_buffer:
                for k, v in scores.items():
                    avg_scores[k] = avg_scores.get(k, 0) + v

            dominant = max(avg_scores, key=avg_scores.get)

            mood_label, mood_score = map_emotion_to_mood(dominant)

            current_mood = mood_label
            current_score = mood_score

            history.append((datetime.now(), current_score))
            if len(history) > 200:
                history[:] = history[-200:]

            append_log(f"Emotion(avg): {dominant} | Mood: {mood_label} | Score: {mood_score}")

            # ---- SERIAL COMMUNICATION ----
            if ser:
                send_mood_via_serial(ser, mood_label)

            # ---- WIFI COMMUNICATION TO ESP32 ----
            if WIFI_ENABLED:
                threading.Thread(
                    target=send_mood_via_wifi,
                    args=(mood_label, mood_score),
                    daemon=True
                ).start()

            # ---- SPOTIFY ----
            if spotify_controller and spotify_controller.logged_in:
                if mood_label in PLAYLISTS:
                    with _spotify_lock:
                        if _last_spotify_call_mood != mood_label:
                            threading.Thread(
                                target=spotify_controller.play_playlist_for_mood,
                                args=(mood_label,),
                                daemon=True
                            ).start()
                            _last_spotify_call_mood = mood_label

        except Exception as e:
            append_log(f"Analysis error: {e}")

        time.sleep(0.2)

# ---------------- UI components ----------------
class SemiCircleMoodGauge(QWidget):
    SEGMENT_COLORS = [
        (231, 76, 60),    # Angry (left)
        (52, 152, 219),   # Sad
        (241, 196, 15),   # Neutral
        (76, 198, 122)    # Happy (right)
    ]

    EMOJI_BY_INDEX = ["😠", "😢", "🙂", "😄"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        global display_score, current_mood

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        padding = 20

        gauge_w = w - padding * 2
        gauge_h = h * 1.8
        size = max(min(gauge_w, gauge_h), 200)

        rect = QRectF(
            (w - size) / 2,
            10,
            size,
            size
        )

        cx = rect.center().x()
        cy = rect.center().y()
        r = rect.width() / 2

        start_angle = 180
        span_angle = 180

        # ---------- Background arc ----------
        painter.setPen(QPen(QColor(30, 30, 30), 26, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, int(start_angle * 16), int(-span_angle * 16))

        # ======================================================
        # 🔥 CORRECT 4-COLOR CONICAL GRADIENT (FIXED)
        # ======================================================
        gradient = QConicalGradient(rect.center(), 270)
        # 270° = leftmost point → perfect for semicircle sweep

        # Duplicate stops to FORCE full coverage of 180°
        gradient.setColorAt(0.00, QColor(231, 76, 60))   # Angry
        gradient.setColorAt(0.25, QColor(52, 152, 219))  # Sad
        gradient.setColorAt(0.50, QColor(241, 196, 15))  # Neutral
        gradient.setColorAt(0.75, QColor(76, 198, 122))  # Happy
        gradient.setColorAt(1.00, QColor(231, 76, 60))   # wrap

        grad_pen = QPen()
        grad_pen.setBrush(gradient)
        grad_pen.setWidth(24)
        grad_pen.setCapStyle(Qt.RoundCap)

        painter.setPen(grad_pen)
        painter.drawArc(rect, int(start_angle * 16), int(-span_angle * 16))

        # ---------- Separators (visual clarity) ----------
        seg_count = 4
        seg_span = span_angle / seg_count

        for i in range(1, seg_count):
            ang = start_angle - i * seg_span
            x1 = cx + math.cos(math.radians(ang)) * (r - 10)
            y1 = cy - math.sin(math.radians(ang)) * (r - 10)
            x2 = cx + math.cos(math.radians(ang)) * (r + 2)
            y2 = cy - math.sin(math.radians(ang)) * (r + 2)
            painter.setPen(QPen(QColor(18, 18, 18), 3))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ---------- Emojis ----------
        for i, emoji in enumerate(self.EMOJI_BY_INDEX):
            mid_ang = start_angle - (i + 0.5) * seg_span
            rad = math.radians(mid_ang)
            ex = cx + math.cos(rad) * (r + 12)
            ey = cy - math.sin(rad) * (r + 12)
            painter.setFont(QFont("Segoe UI Emoji", 18))
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(QPointF(ex - 12, ey + 6), emoji)

        # ---------- Inner circle ----------
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 18, 18))
        inner_r = r * 0.36
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # ---------- Ticks ----------
        for i in range(11):
            ang = start_angle - (i * span_angle / 10)
            rad = math.radians(ang)
            x1 = cx + math.cos(rad) * (r - 8)
            y1 = cy - math.sin(rad) * (r - 8)
            x2 = cx + math.cos(rad) * (r - 18)
            y2 = cy - math.sin(rad) * (r - 18)
            painter.setPen(QPen(QColor(25, 25, 25), 2))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ---------- Needle ----------
        angle = 180 - (display_score / 100.0) * 180.0
        rad = math.radians(angle)
        nx = cx + math.cos(rad) * (inner_r * 1.6)
        ny = cy - math.sin(rad) * (inner_r * 1.6)

        for i, a in enumerate([40, 25, 15]):
            painter.setPen(QPen(QColor(255, 255, 255, a), 20 + i * 8, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(cx, cy), QPointF(nx, ny))

        painter.setPen(QPen(Qt.white, 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(cx, cy), QPointF(nx, ny))

        painter.setBrush(QColor(32, 32, 32))
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        painter.drawEllipse(QPointF(cx, cy), inner_r * 0.18, inner_r * 0.18)

        # ---------- Label ----------
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.setPen(QColor(230, 230, 230))
        painter.drawText(
            QRectF(0, rect.bottom() + 6, w, 40),
            Qt.AlignHCenter,
            f"{current_mood} — {int(display_score)}%"
        )

class EmoteLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_font_size = 32
        self.phase = 0.0
        self.setAlignment(Qt.AlignCenter)
        self.setText("🙂")
    def animate(self):
        global current_mood
        mapping = {
            "HAPPY": "😄",
            "NEUTRAL": "🙂",
            "SAD": "😔",
            "ANGRY": "😠",
            "UNKNOWN": "🤖"
        }

        self.setText(mapping.get(current_mood, "🤖"))

        self.phase += 0.18
        scale = 1.0 + 0.08 * math.sin(self.phase)
        opacity = 200 + int(55 * math.sin(self.phase))

        font = QFont("Segoe UI Emoji", int(34 * scale))
        self.setFont(font)
        self.setStyleSheet(f"color: rgba(255,255,255,{opacity});")

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=4, height=2.2, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        fig.tight_layout()
    def plot_history(self, hist):
        self.axes.cla()
        if not hist:
            self.axes.text(0.5, 0.5, "No data yet", ha='center', va='center')
            self.draw()
            return
        times, scores = zip(*hist)
        self.axes.plot_date(times, scores, '-', linewidth=2)
        self.axes.set_ylim(0, 100)
        self.axes.set_ylabel("Stress / Mood Score")
        self.axes.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.axes.grid(alpha=0.3)
        self.axes.set_title("Mood / Stress over time")
        self.draw()

# Main window
class AdvancedMoodApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mood Detector — Advanced UI (Semi-circle Gauge)")
        self.resize(1500, 700)
        self.setMinimumSize(980, 560)
        self.setup_ui()
        self.ui_timer = QTimer()
        self.ui_timer.setInterval(50)
        self.ui_timer.timeout.connect(self.on_ui_timer)
        self.ui_timer.start()
        self.emoji_timer = QTimer()
        self.emoji_timer.setInterval(120)
        self.emoji_timer.timeout.connect(self.on_emoji_timer)
        self.emoji_timer.start()
        self._last_log_index = 0
        self._last_history_len = 0

        # runtime flag visible to UI if needed
        self.playlist_active_flag = False

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #0f1112; color: #e8e8e8; font-family: "Segoe UI"; }
            QPushButton {
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2c3e50,
                    stop:1 #16a085
                );
                border-radius: 14px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
                color: #ffffff;
                border: none;
            }

            QPushButton:hover {
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 #26333D,
                    stop:1 #1D7A68
                );
            }

            QPushButton:pressed {
                background: #212529;
            }
            QLabel { color: #e8e8e8; }
            QTextEdit { background-color: #0B0B0C; color: #dcdcdc; border: 1px solid #222; border-radius:6px; }
            QFrame#panel { background-color: #0d0e0f; border-radius: 10px; border: 1px solid #1a1a1a; }
        """)
        main_layout = QHBoxLayout(self)
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)

        # ---- Semi-circle gauge ----
        self.gauge = SemiCircleMoodGauge()
        panel_layout.addWidget(self.gauge, alignment=Qt.AlignCenter)

        # ---- Emoji + Mood Label Row ----
        em_row = QHBoxLayout()
        self.emoji = EmoteLabel()
        self.emoji.setFixedWidth(100)
        em_row.addWidget(self.emoji, alignment=Qt.AlignLeft)
        self.mood_text = QLabel("Mood: UNKNOWN")
        self.mood_text.setFont(QFont("Segoe UI", 14))
        em_row.addWidget(self.mood_text, alignment=Qt.AlignVCenter)
        panel_layout.addLayout(em_row)

        # ---- Spotify Currently Playing Label ----
        self.spotify_song_label = QLabel("🎵 Not playing")
        self.spotify_song_label.setFont(QFont("Segoe UI", 12))
        self.spotify_song_label.setAlignment(Qt.AlignHCenter)
        panel_layout.addWidget(self.spotify_song_label)

        # ---- Buttons row ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.start_btn = QPushButton("Start Detection")
        self.start_btn.clicked.connect(self.start_detection)
        self.stop_btn = QPushButton("Stop Detection")
        self.stop_btn.clicked.connect(self.stop_detection)
        self.exit_btn = QPushButton("Exit")
        self.exit_btn.clicked.connect(self.close_app)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.exit_btn)

        # Spotify login button
        self.spotify_btn = QPushButton("Login to Spotify")
        self.spotify_btn.setIcon(QIcon("spotify.png"))
        self.spotify_btn.setIconSize(QSize(22, 22))
        self.spotify_btn.clicked.connect(self.spotify_login_clicked)
        btn_row.addWidget(self.spotify_btn)

        panel_layout.addLayout(btn_row)
        left_col.addWidget(panel)

        self.set_playlist_btn = QPushButton("Set Mood Playlists")
        self.set_playlist_btn.clicked.connect(self.open_playlist_dialog)
        btn_row.addWidget(self.set_playlist_btn)

        # ---- Right side: graph + log + status ----
        right_top = QFrame()
        right_top.setObjectName("panel")
        rt_layout = QVBoxLayout(right_top)
        rt_layout.setContentsMargins(12, 12, 12, 12)
        self.canvas = MplCanvas(self, width=6, height=3, dpi=100)
        rt_layout.addWidget(self.canvas)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setFixedHeight(220)
        rt_layout.addWidget(self.log_widget)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Status: Stopped")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                padding: 6px 12px;
                border-radius: 10px;
                font-weight: 600;
            }
        """)
        status_row.addWidget(self.status_label)

        # WiFi status indicator
        self.wifi_status = QLabel(f"WiFi: {'Enabled' if WIFI_ENABLED else 'Disabled'} | Server: Connected")
        self.wifi_status.setFont(QFont("Segoe UI", 9))
        self.wifi_status.setStyleSheet("""
            QLabel {
                background-color: #16a085;
                padding: 6px 12px;
                border-radius: 10px;
                font-size: 10px;
            }
        """)
        status_row.addWidget(self.wifi_status)

        rt_layout.addLayout(status_row)
        right_col.addWidget(right_top)
        main_layout.addLayout(left_col, stretch=2)
        main_layout.addLayout(right_col, stretch=3)

    def open_playlist_dialog(self):
        if not spotify_controller or not spotify_controller.logged_in:
            QMessageBox.warning(self, "Spotify", "Login to Spotify first")
            return

        mood, ok = QInputDialog.getItem(self, "Mood", "Select mood:", MOODS, 0, False)
        if not ok:
            return

        try:
            r = requests.get(
                "https://api.spotify.com/v1/me/playlists?limit=50",
                headers=spotify_controller.api_headers(),
                timeout=10
            )
            playlists = r.json().get("items", [])

            dlg = QDialog(self)
            dlg.setWindowTitle("Select Playlist")
            layout = QVBoxLayout(dlg)
            listw = QListWidget()

            for p in playlists:
                item = QListWidgetItem(p["name"])
                item.setData(Qt.UserRole, p["uri"])
                listw.addItem(item)

            layout.addWidget(listw)
            btn = QPushButton("Save")
            layout.addWidget(btn)

            def save_selected():
                item = listw.currentItem()
                if item:
                    PLAYLISTS[mood] = item.data(Qt.UserRole)
                    save_playlists(PLAYLISTS)
                    append_log(f"[Playlist] {mood} playlist saved")
                    dlg.accept()

            btn.clicked.connect(save_selected)
            dlg.exec_()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def set_spotify_connected_ui(self):
        self.spotify_btn.setText("Spotify Connected ✅")
        self.spotify_btn.setEnabled(False)
        self.spotify_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2c3e50,
                    stop:1 #16a085
                );
                color: white;
                border-radius: 14px;
                padding: 12px 18px;
                font-weight: 600;
            }
        """)
    
    def on_ui_timer(self):
        global display_score, current_score, current_mood, history, log_lines
        if display_score < current_score:
            diff = current_score - display_score
            step = max(1, int(diff * 0.14))
            display_score += step
            if display_score > current_score:
                display_score = current_score
        elif display_score > current_score:
            diff = display_score - current_score
            step = max(1, int(diff * 0.14))
            display_score -= step
            if display_score < current_score:
                display_score = current_score
        self.mood_text.setText(f"Mood: {current_mood}")
        self.gauge.update()
        if self._last_log_index < len(log_lines):
            new = log_lines[self._last_log_index:]
            self._last_log_index = len(log_lines)
            for ln in new:
                self.log_widget.append(ln)
            self.log_widget.ensureCursorVisible()
        if len(history) != self._last_history_len:
            self._last_history_len = len(history)
            self.canvas.plot_history(history[-120:])

        # update Spotify song info every ~2 seconds
        if hasattr(self, "_last_spotify_update") is False:
            self._last_spotify_update = 0

        now = time.time()
        if now - self._last_spotify_update > 2.0:
            self._last_spotify_update = now
            threading.Thread(target=self.update_spotify_song_info, daemon=True).start()
    
    def on_emoji_timer(self):
        self.emoji.animate()

    def start_detection(self):
        global running, cam, ser
        if running:
            QMessageBox.information(self, "Info", "Detection already running!")
            return
        running = True
        if SERIAL_AVAILABLE and ser is None:
            try:
                ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
                time.sleep(1)
                append_log(f"[Serial] Opened {SERIAL_PORT}")
            except Exception as e:
                append_log(f"[Serial] Could not open {SERIAL_PORT}: {e}")
        cam = cv2.VideoCapture(WEBCAM_INDEX)
        if not cam.isOpened():
            QMessageBox.critical(self, "Error", "Cannot open webcam")
            running = False
            return
        append_log("Starting detection thread")
        threading.Thread(target=detect_mood, daemon=True).start()
        self.status_label.setText("Status: Running")
        if WIFI_ENABLED:
            append_log("[WiFi] Using Node.js relay server")


    def stop_detection(self):
        global running, cam, ser
        if not running:
            QMessageBox.information(self, "Info", "Detection not running")
            return
        running = False
        time.sleep(0.3)
        if cam:
            cam.release()
        if ser:
            try:
                ser.close()
            except:
                pass
        append_log("Stopped detection")
        self.status_label.setText("Status: Stopped")

    def close_app(self):
        self.stop_detection()
        stop_face_tracker()
        QApplication.quit()

    def spotify_login_clicked(self):
        global spotify_controller
        if spotify_controller and spotify_controller.logged_in:
            QMessageBox.information(self, "Spotify", "Already logged in.")
            return
        if not spotify_controller:
            QMessageBox.critical(self, "Spotify", "Spotify controller not initialized.")
            return
        # Launch interactive authorization in thread because start_local_server will block
        threading.Thread(target=self.spotify_authorize_flow, daemon=True).start()

    def spotify_authorize_flow(self):
        global spotify_controller
        append_log("[Spotify] Starting interactive authorization...")
        spotify_controller.authorize_interactively()
        if spotify_controller.logged_in:
            self.set_spotify_connected_ui()
            append_log("[Spotify] Logged in OK. You can now play music from this app.")
            # optionally auto-play a short sample or ensure playback device exists
        else:
            append_log("[Spotify] Login did not complete.")

    def update_spotify_song_info(self):
        global spotify_controller
        if not spotify_controller or not spotify_controller.logged_in:
            self.spotify_song_label.setText("🎵 Not connected")
            return
        try:
            r = requests.get("https://api.spotify.com/v1/me/player/currently-playing",
                            headers=spotify_controller.api_headers(), timeout=5)
            if r.status_code == 200 and r.json():
                data = r.json()
                item = data.get("item")
                if item:
                    name = item.get("name")
                    artists = ", ".join([a['name'] for a in item.get("artists", [])])
                    self.spotify_song_label.setText(f"🎵 {name} — {artists}")
                    return
            self.spotify_song_label.setText("🎵 Nothing playing")
        except:
            self.spotify_song_label.setText("🎵 Error fetching song")
    
# ---------------- Spotify monitor ----------------
def spotify_playback_monitor_loop():
    global spotify_controller, spotify_playing
    while True:
        try:
            with spotify_playing_lock: playing_flag = spotify_playing
            if playing_flag and spotify_controller and spotify_controller.logged_in:
                state = spotify_controller.get_playback_state()
                if state and not state.get("is_playing", False):
                    with spotify_playing_lock: spotify_playing = False
        except: pass
        time.sleep(3.0)

# ---------------- Run App ----------------
def main():
    global spotify_controller
    app = QApplication(sys.argv)
    msg = QMessageBox.question(None, "Permission", "Allow webcam access?", QMessageBox.Yes|QMessageBox.No)
    if msg != QMessageBox.Yes: return
    start_face_tracker()
    spotify_controller = SpotifyController(SPOTIFY_CLIENT_ID, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES)
    threading.Thread(target=spotify_playback_monitor_loop, daemon=True).start()
    win = AdvancedMoodApp()
    win.show()
    sys.exit(app.exec_())

if __name__=="__main__":
    main()

atexit.register(stop_face_tracker)
