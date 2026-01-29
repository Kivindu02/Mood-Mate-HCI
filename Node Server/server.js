import express from "express";
import cors from "cors";

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// ================================
// SERVER STATE (IN-MEMORY)
// ================================
let latestMood = "ROUND";
let lastUpdated = Date.now();

let latestAngle = 90;
let angleUpdated = 0;
let angleValid = false;

// ================================
// ROUTES
// ================================

// Health check
app.get("/", (req, res) => {
  res.json({
    status: "OK",
    service: "Mood Relay Server",
    latestMood,
    lastUpdated
  });
});

// Python app sends mood here
app.post("/update-mood", (req, res) => {
  const { mood } = req.body;

  if (!mood) {
    return res.status(400).json({ error: "Mood is required" });
  }

  latestMood = String(mood).trim().toUpperCase();
  lastUpdated = Date.now();

  console.log(`[UPDATE] Mood set to: ${latestMood}`);

  res.json({
    success: true,
    mood: latestMood
  });
});

// ESP32 fetches mood from here
app.get("/get-mood", (req, res) => {
  res.set("Cache-Control", "no-store");
  res.json({ mood: latestMood });
});

// Python sends angle
app.post("/update-angle", (req, res) => {
  const { angle } = req.body;

  if (typeof angle !== "number") {
    return res.status(400).json({ error: "Angle required" });
  }

  latestAngle = Math.max(0, Math.min(180, angle));
  angleUpdated = Date.now();
  angleValid = true;

  console.log(`[UPDATE] Angle: ${latestAngle}`);
  res.json({ success: true });
});

// ESP32 fetches angle
app.get("/get-angle", (req, res) => {
  res.set("Cache-Control", "no-store");
  res.json({
    angle: latestAngle,
    valid: angleValid   // 🔴 SEND VALID FLAG
  });
});

// ================================
// START SERVER
// ================================
app.listen(PORT, () => {
  console.log("====================================");
  console.log(" Mood Relay Server RUNNING");
  console.log(` Port: ${PORT}`);
  console.log("====================================");
});
