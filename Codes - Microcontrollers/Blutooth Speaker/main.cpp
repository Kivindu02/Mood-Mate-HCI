#include <Arduino.h>
#include "BluetoothA2DPSink.h"

BluetoothA2DPSink a2dp_sink;

/*
 I2S PIN CONFIGURATION
 ESP32 DevKit v1 + MAX98357A
*/
i2s_pin_config_t i2s_pins = {
    .bck_io_num = 26,    // BCLK
    .ws_io_num  = 25,    // LRC / WS
    .data_out_num = 22,  // DIN
    .data_in_num = I2S_PIN_NO_CHANGE
};

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("Starting ESP32 Bluetooth Speaker...");

    // Set I2S pins
    a2dp_sink.set_pin_config(i2s_pins);

    // Optional: volume limit (0–127)
    a2dp_sink.set_volume(90);

    // Start Bluetooth with device name
    a2dp_sink.start("ESP32_Mood_Speaker");

    Serial.println("Bluetooth speaker ready!");
    Serial.println("Pair your PC with 'ESP32_Mood_Speaker'");
}

void loop() {
    // Nothing needed here
}
