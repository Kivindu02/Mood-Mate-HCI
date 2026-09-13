<div align="center">

# 🤖 Mood-Mate HCI

### *A Human-Computer Interaction System for Real-Time Emotion-Aware Robotics & Wellness*

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-Desktop_UI-41CD52?logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![DeepFace](https://img.shields.io/badge/DeepFace-Emotion_AI-FF6F00?logo=tensorflow&logoColor=white)](https://github.com/serengil/deepface)
[![ESP32](https://img.shields.io/badge/ESP32-IoT_Hardware-E7352C?logo=espressif&logoColor=white)](https://www.espressif.com/)
[![Spotify](https://img.shields.io/badge/Spotify-Music_Therapy-1DB954?logo=spotify&logoColor=white)](https://developer.spotify.com/)
[![License](https://img.shields.io/badge/License-Academic-blue)]()

---

**Mood-Mate** is a multimodal, emotion-responsive companion robot built around **Human-Computer Interaction (HCI)** principles. It combines **real-time facial emotion recognition**, a **physical robotic embodiment** with expressive OLED eyes, a **servo-based face-tracking head**, a **Bluetooth speaker for mood-adaptive music**, and a polished **desktop GUI** — all working in concert to create a deeply personalized wellness experience.

[Overview](#project-overview) · [Tech Stack](#tech-stack) · [Architecture](#hci-design--user-flow) · [Features](#key-features--ux-principles) · [Setup](#environment--installation-setup) · [Run](#local-execution--testing)

</div>

---

## 📋 Project Overview

### The Vision

Mood-Mate addresses a critical gap in emotional wellness technology: most mood-tracking apps are **passive** — they ask users to self-report feelings. Mood-Mate flips this paradigm by **actively sensing** the user's emotional state through computer vision, then **responding** across multiple physical and digital channels simultaneously.

### Target Audience

| Audience | Use Case |
|---|---|
| **HCI Researchers** | A reference platform for studying embodied emotion-aware interfaces, multimodal feedback loops, and affective computing pipelines |
| **Wellness & Therapy Spaces** | Ambient companion that monitors emotional trends and provides non-intrusive music-based interventions |
| **Maker / IoT Enthusiasts** | A fully integrated ESP32 + Python + Cloud system demonstrating real-time hardware-software coordination |
| **Students & Educators** | A capstone-grade project showcasing DeepFace, PyQt5, servo control, OLED animation, and REST APIs in a single cohesive system |

### User-Centered Design Philosophy

Mood-Mate is grounded in established HCI principles:

- **🎯 Non-Intrusive Sensing** — Emotion detection runs passively via webcam; the user never needs to manually log a mood entry.
- **🔄 Continuous Feedback Loop** — Detected emotions are reflected back to the user through a rich desktop gauge, animated robot eyes, and curated music — closing the perception-action loop.
- **🧠 Affect-Aware Adaptation** — The system adapts its behavior (eye expression, music genre, head orientation) to the user's current emotional state, respecting the principle of *adaptive interfaces*.
- **♿ Graceful Degradation** — Hardware components (serial, Wi-Fi, ESP32, Spotify) are all optional. The system operates in a reduced-but-functional mode when any subsystem is unavailable.
- **🛡️ Permission-First Design** — Webcam access requires explicit user consent via a dialog prompt before any detection begins.

### Core Wellness Objectives

1. **Ambient Emotion Monitoring** — Continuously track facial emotions without requiring conscious user effort.
2. **Music-Based Mood Regulation** — Automatically play mood-matched Spotify playlists as a form of passive music therapy.
3. **Visual Trend Analytics** — Render real-time mood score charts so users can identify emotional patterns over time.
4. **Embodied Empathic Response** — Through animated OLED robot eyes that mirror the user's detected emotion, creating a sense of *social presence*.

---

## 🛠 Tech Stack

### Software Components

| Layer | Technology | Role |
|---|---|---|
| **Desktop UI / Frontend** | [PyQt5](https://riverbankcomputing.com/software/pyqt/) | Main GUI framework — semi-circle mood gauge, emoji animations, log panel, control buttons |
| **Emotion Recognition (ML)** | [DeepFace](https://github.com/serengil/deepface) (RetinaFace backend) | Real-time facial emotion analysis (7 emotions → 4 mood categories) |
| **Face Detection / Tracking** | [MediaPipe](https://mediapipe.dev/) Face Detection | Headless face tracking for servo-driven pan control |
| **Computer Vision** | [OpenCV](https://opencv.org/) (`cv2`) | Webcam capture, frame preprocessing (grayscale equalization) |
| **Data Visualization** | [Matplotlib](https://matplotlib.org/) (Qt5Agg backend) | Live mood-score time-series chart embedded in the GUI |
| **Music Integration** | [Spotify Web API](https://developer.spotify.com/documentation/web-api/) (PKCE OAuth 2.0) | Mood-adaptive playlist playback with full device management |
| **Relay Server** | [Node.js](https://nodejs.org/) + [Express](https://expressjs.com/) | Cloud-hosted REST relay bridging the Python app and ESP32 microcontrollers |
| **Serial Communication** | [PySerial](https://pyserial.readthedocs.io/) | Optional direct USB-serial link to ESP32 hardware |

### Hardware / Embedded Components

| Module | Microcontroller | Peripheral | Function |
|---|---|---|---|
| **Emotion Eyes** | ESP32 DevKit | SSD1306 128×64 OLED | Animated robot eyes ([FluxGarage RoboEyes](https://github.com/FluxGarage/RoboEyes)) that change expression based on detected mood |
| **Face Tracker** | ESP32 DevKit | SG90 Servo Motor | Pan-servo head that follows the user's face in real time |
| **Bluetooth Speaker** | ESP32 DevKit | MAX98357A I2S DAC | A2DP Bluetooth audio sink — the robot's built-in speaker for Spotify playback |

### Infrastructure

| Service | Purpose |
|---|---|
| [Render](https://render.com/) | Cloud hosting for the Node.js mood relay server (`mood-relay-server.onrender.com`) |
| WiFiManager (ESP32) | Captive portal for zero-config Wi-Fi provisioning on all ESP32 modules |

---

## 🔀 HCI Design & User Flow

The following diagram illustrates the complete interaction architecture — from user presence through emotion sensing, multimodal feedback, and adaptive response:

```mermaid
flowchart TB
    subgraph USER["👤 User"]
        U_FACE["Facial Expression"]
        U_POSITION["Head Position"]
    end

    subgraph SENSING["🔍 Perception Layer (Python)"]
        WEBCAM["📷 Webcam Capture<br/><i>OpenCV</i>"]
        DEEPFACE["🧠 Emotion Analysis<br/><i>DeepFace + RetinaFace</i>"]
        SMOOTHER["📊 Emotion Smoothing<br/><i>Rolling Window (n=5)</i>"]
        MAPPER["🎯 Mood Mapper<br/><i>7 emotions → 4 moods</i>"]
        FACETRACK["👁️ Face Tracker<br/><i>MediaPipe</i>"]
    end

    subgraph PROCESSING["⚙️ Decision Layer"]
        MOOD_STATE["Mood State<br/>HAPPY · NEUTRAL · SAD · ANGRY"]
        SCORE["Mood Score<br/>0 – 100"]
        ANGLE["Pan Angle<br/>0° – 180°"]
    end

    subgraph OUTPUT_DIGITAL["🖥️ Digital Feedback (PyQt5 GUI)"]
        GAUGE["🌡️ Semi-Circle<br/>Mood Gauge"]
        EMOJI["😄 Animated<br/>Emoji"]
        CHART["📈 Live Mood<br/>Trend Chart"]
        LOG["📝 Activity<br/>Log Panel"]
        STATUS["🔋 Status<br/>Indicators"]
    end

    subgraph RELAY["☁️ Cloud Relay"]
        NODE["Node.js Server<br/><i>Render</i>"]
    end

    subgraph OUTPUT_PHYSICAL["🤖 Physical Feedback (ESP32 Robot)"]
        EYES["👀 OLED Robot Eyes<br/><i>Mood-matched expressions</i>"]
        SERVO["🔄 Pan Servo<br/><i>Face-following head</i>"]
        SPEAKER["🔊 BT Speaker<br/><i>A2DP Audio Sink</i>"]
    end

    subgraph MUSIC["🎵 Music Therapy"]
        SPOTIFY["Spotify API<br/><i>PKCE OAuth 2.0</i>"]
        PLAYLIST["Mood Playlists<br/><i>User-configurable</i>"]
    end

    U_FACE --> WEBCAM
    U_POSITION --> WEBCAM
    WEBCAM --> DEEPFACE
    WEBCAM --> FACETRACK
    DEEPFACE --> SMOOTHER --> MAPPER
    MAPPER --> MOOD_STATE
    MAPPER --> SCORE
    FACETRACK --> ANGLE

    MOOD_STATE --> GAUGE
    MOOD_STATE --> EMOJI
    SCORE --> CHART
    MOOD_STATE --> LOG
    SCORE --> STATUS

    MOOD_STATE -->|"POST /update-mood"| NODE
    ANGLE -->|"POST /update-angle"| NODE
    NODE -->|"GET /get-mood"| EYES
    NODE -->|"GET /get-angle"| SERVO

    MOOD_STATE --> SPOTIFY
    SPOTIFY --> PLAYLIST
    PLAYLIST -->|"Bluetooth A2DP"| SPEAKER

    style USER fill:#1a1a2e,stroke:#e94560,color:#fff
    style SENSING fill:#16213e,stroke:#0f3460,color:#fff
    style PROCESSING fill:#0f3460,stroke:#533483,color:#fff
    style OUTPUT_DIGITAL fill:#1a1a2e,stroke:#1db954,color:#fff
    style RELAY fill:#2d3436,stroke:#6c5ce7,color:#fff
    style OUTPUT_PHYSICAL fill:#1a1a2e,stroke:#e17055,color:#fff
    style MUSIC fill:#1a1a2e,stroke:#1db954,color:#fff
