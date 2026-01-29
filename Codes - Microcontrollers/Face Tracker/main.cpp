#include <WiFi.h>
#include <WiFiManager.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>

// ================= SERVO =================
Servo panServo;
const int SERVO_PIN = 18;

int currentAngle = 90;
int targetAngle  = 90;
const int SMOOTH_SPEED = 5;

// ================= NODE SERVER =================
const char* SERVER_URL = "https://mood-relay-server.onrender.com/get-angle"; 
// 🔴 Change ONLY this IP

// ================= POLLING =================
unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL = 80;

// ================= BOOT CONTROL =================
unsigned long bootTime = 0;
const unsigned long BOOT_IGNORE_TIME = 3000;
bool waitingForFreshAngle = true;

// ================= FETCH ANGLE =================
bool fetchAngleFromServer(int &outAngle, bool &isValid) {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;

  http.begin(client, SERVER_URL);
  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();

    int aIdx = payload.indexOf("\"angle\"");
    int vIdx = payload.indexOf("\"valid\"");

    if (aIdx >= 0 && vIdx >= 0) {
      outAngle = payload.substring(payload.indexOf(":", aIdx) + 1).toInt();
      isValid  = payload.substring(payload.indexOf(":", vIdx) + 1).startsWith("true");

      outAngle = constrain(outAngle, 0, 180);
      http.end();
      return true;
    }
  }

  http.end();
  return false;
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================");
  Serial.println("ESP32 Webcam Head Controller - STARTING");
  Serial.println("========================================");

  // ================= SERVO INIT =================
  ESP32PWM::allocateTimer(0);
  panServo.setPeriodHertz(50);
  panServo.attach(SERVO_PIN, 500, 2400);
  panServo.write(currentAngle);

  // ================= WIFI MANAGER =================
  WiFiManager wm;
  wm.setTimeout(180);
  wm.setConfigPortalBlocking(true);

  // 🔥 CLEAR WIFI EVERY BOOT (same as OLED)
  wm.resetSettings();

  if (!wm.autoConnect("ESP32-Head-Setup")) {
    Serial.println("WiFi failed, restarting...");
    ESP.restart();
  }

  Serial.println("WiFi Connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  bootTime = millis();

  targetAngle = currentAngle = 90;
  panServo.write(90);

  waitingForFreshAngle = true;

  Serial.println("[BOOT] Waiting for fresh angle from server...");
}

// ================= LOOP =================
void loop() {

  // ===== Poll server =====
  if (millis() - lastPollTime >= POLL_INTERVAL) {
    lastPollTime = millis();

    int newAngle;
    bool valid;

    if (fetchAngleFromServer(newAngle, valid)) {

      if (!valid) {
        // 🔴 Ignore until Python sends
        return;
      }

      if (waitingForFreshAngle) {
        Serial.println("[READY] First valid angle received");
        waitingForFreshAngle = false;
      }

      if (newAngle != targetAngle) {
        Serial.println("NEW TARGET ANGLE: " + String(newAngle));
        targetAngle = newAngle;
      }
    }
  }

  // Smooth servo
  if (currentAngle < targetAngle)
    currentAngle = min(currentAngle + SMOOTH_SPEED, targetAngle);
  else if (currentAngle > targetAngle)
    currentAngle = max(currentAngle - SMOOTH_SPEED, targetAngle);

  panServo.write(currentAngle);
  delay(20);

  // ===== Status every 10s =====
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 10000) {
    lastStatus = millis();
    Serial.println("[STATUS] WiFi: " +
      String(WiFi.status() == WL_CONNECTED ? "Connected" : "Disconnected") +
      " | Angle: " + String(currentAngle));
  }
}
