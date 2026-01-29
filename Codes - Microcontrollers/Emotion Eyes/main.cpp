#include <WiFi.h>
#include <WiFiManager.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <FluxGarage_RoboEyes.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ================= OLED =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
RoboEyes<Adafruit_SSD1306> roboEyes(display);

// ================= CLOUD SERVER =================
const char* SERVER_URL = "https://mood-relay-server.onrender.com/get-mood";

// Polling control
unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL = 2500;

unsigned long bootTime = 0;
const unsigned long BOOT_IGNORE_TIME = 6000; // 6 seconds

bool waitingForFreshMood = true;

// ================= STATE =================
String INITIAL_MOOD = "ROUND";
String lastMood = "ROUND";

bool fetchMoodFromServer(String &outMood) {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClientSecure client;
  client.setInsecure();
  
  HTTPClient http;
  http.setTimeout(3000);
  http.begin(SERVER_URL);

  int httpCode = http.GET();
  if (httpCode == 200) {
    String payload = http.getString();

    // Expecting: { "mood": "HAPPY" }
    int moodIndex = payload.indexOf("\"mood\"");
    if (moodIndex >= 0) {
      int colon = payload.indexOf(":", moodIndex);
      int q1 = payload.indexOf("\"", colon + 1);
      int q2 = payload.indexOf("\"", q1 + 1);
      outMood = payload.substring(q1 + 1, q2);
      outMood.trim();
      http.end();
      return true;
    }
  }

  http.end();
  return false;
}

// ================= SET MOOD =================
void applyMood(String mood) {
  mood.trim();
  mood.toUpperCase();

  Serial.println("========================================");
  Serial.println("APPLYING MOOD: [" + mood + "]");
  Serial.print("Mood length: ");
  Serial.println(mood.length());
  
  // Debug: print each character
  Serial.print("Characters: ");
  for (int i = 0; i < mood.length(); i++) {
    Serial.print((int)mood[i]);
    Serial.print(" ");
  }
  Serial.println();

  if (mood == "HAPPY") {
    Serial.println(">>> Setting HAPPY eyes");
    roboEyes.setMood(MOOD_HAPPY);
    roboEyes.setAutoblinker(ON, 2, 1);
    roboEyes.setIdleMode(ON);
    roboEyes.anim_laugh();
  }
  else if (mood == "ANGRY") {
    Serial.println(">>> Setting ANGRY eyes");
    roboEyes.setMood(MOOD_ANGRY);
    roboEyes.setAutoblinker(ON, 2, 1);
    roboEyes.setIdleMode(ON);
    roboEyes.setHFlicker(ON, 10);
  }
  else if (mood == "SAD") {
    Serial.println(">>> Setting SAD eyes");
    roboEyes.setMood(MOOD_TIRED);
    roboEyes.setAutoblinker(ON, 3, 1);
    roboEyes.setIdleMode(ON);
  }
  else if (mood == "NEUTRAL") {
    Serial.println(">>> Setting NEUTRAL eyes");
    roboEyes.setMood(MOOD_LINE);
    roboEyes.setAutoblinker(ON, 3, 1);
    roboEyes.setIdleMode(ON);
    roboEyes.setHFlicker(OFF);
  }
  else if (mood == "ROUND") {
    Serial.println(">>> Setting ROUND eyes");
    roboEyes.setMood(MOOD_ROUND);
    roboEyes.setAutoblinker(ON, 3, 1);
    roboEyes.setIdleMode(ON);
    roboEyes.setHFlicker(OFF);
  }
  else {
    Serial.println(">>> UNKNOWN mood, setting DEFAULT");
    roboEyes.setMood(MOOD_ROUND);
    roboEyes.setAutoblinker(ON, 3, 1);
    roboEyes.setIdleMode(ON);
    roboEyes.setHFlicker(OFF);
  }
  Serial.println("========================================\n");
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n========================================");
  Serial.println("ESP32 RoboEyes Mood Receiver - STARTING");
  Serial.println("========================================\n");

  // OLED init
  Serial.print("Initializing OLED... ");
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("FAILED!");
    Serial.println("Check OLED connections!");
    while (true) {
      delay(1000);
    }
  }
  Serial.println("OK");

  display.clearDisplay();
  display.display();

  // RoboEyes init
  Serial.print("Initializing RoboEyes... ");
  roboEyes.begin(SCREEN_WIDTH, SCREEN_HEIGHT, 60);
  roboEyes.setCyclops(ON);     // single eye
  roboEyes.setIdleMode(ON);
  roboEyes.setAutoblinker(ON);
  Serial.println("OK");

  // Center eye
  roboEyes.eyeLwidthNext  = 60;
  roboEyes.eyeLheightNext = 40;
  roboEyes.eyeLborderRadiusNext = 8;
  roboEyes.eyeLxNext = (SCREEN_WIDTH  - roboEyes.eyeLwidthNext) / 2;
  roboEyes.eyeLyNext = (SCREEN_HEIGHT - roboEyes.eyeLheightNext) / 2;

  // WiFi connect
  WiFiManager wm;
  wm.setTimeout(180);

  // 🔥 IMPORTANT: DO NOT SAVE WIFI CREDENTIALS
  wm.setConfigPortalBlocking(true);
  wm.setSaveConfigCallback([](){
    Serial.println("WiFi config attempted");
  });

  // 🔥 THIS LINE SOLVES YOUR PROBLEM
  wm.resetSettings();   // <--- clears saved WiFi every boot

  if (!wm.autoConnect("ESP32-Mood-Setup")) {
    Serial.println("WiFi failed, restarting...");
    ESP.restart();
  }


  Serial.println("WiFi Connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  // Start UDP
  // Start UDP (FIXED)
  delay(500);               // 🔥 give WiFi stack time

  bootTime = millis();

  lastMood = "ROUND";
  applyMood("ROUND");

  // 🔥 Force ESP to wait for NEW mood
  waitingForFreshMood = true;

  Serial.println("[BOOT] Waiting for fresh mood from server...");

}

// ================= LOOP =================
void loop() {

  // ===== Poll server for mood =====
  if (millis() - lastPollTime >= POLL_INTERVAL) {
    lastPollTime = millis();

    String newMood;
    if (fetchMoodFromServer(newMood)) {
      if (waitingForFreshMood) {
        // Ignore first reply (stale server state)
        Serial.println("[BOOT] Ignoring stale server mood: " + newMood);
        lastMood = newMood;          // sync state
        waitingForFreshMood = false;
        return;
      }

      if (newMood.length() > 0 && newMood != lastMood) {
        Serial.println("NEW MOOD DETECTED: " + newMood);
        lastMood = newMood;
        applyMood(newMood);
      }
    }


  }
  // ===== RoboEyes engine =====
  roboEyes.update();

  // ===== Status every 10 sec =====
  static unsigned long lastStatusPrint = 0;
  if (millis() - lastStatusPrint > 10000) {
    lastStatusPrint = millis();
    Serial.println("\n[STATUS] WiFi: " +
      String(WiFi.status() == WL_CONNECTED ? "Connected" : "Disconnected") +
      " | IP: " + WiFi.localIP().toString() +
      " | Mood: " + lastMood);
  }
}