/*
 * Phase 1 — IR transmit proof (ESP32-S3)
 *
 * Sends one IR power code every 3 seconds. Point it at the target device.
 * Pass gate: the device powers off/on. Sanity check: watch the IR LED
 * through your phone's SELFIE camera — it should flash purple.
 *
 * Wiring (salvaged NPN transistor, e.g. S8050/2N2222):
 *   GPIO4 ──1kΩ──> transistor BASE
 *   transistor EMITTER ──> GND
 *   3V3 ──~100Ω──> IR LED anode(+) ──> IR LED cathode(-) ──> transistor COLLECTOR
 *
 * Library: IRremoteESP8266 (>= 2.9.0 for S3) via Arduino Library Manager.
 * Board: "ESP32S3 Dev Module", ESP32 Arduino core 3.x.
 */

#include <IRremoteESP8266.h>
#include <IRsend.h>

const uint16_t kIrLedPin = 4;
IRsend irsend(kIrLedPin);

// ── Target: Samsung TV power toggle (works across nearly all Samsung TVs) ──
const uint64_t kCode = 0xE0E040BF;
// Other brands for later:
// LG TV power (NEC):  irsend.sendNEC(0x20DF10EF, 32);
// Sony TV power:      irsend.sendSony(0xA90, 12, 2);  // Sony wants 2+ repeats
// ──────────────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  irsend.begin();
  Serial.println("Phase 1 IR test: sending Samsung power 0xE0E040BF every 3s");
}

void loop() {
  irsend.sendSAMSUNG(kCode, 32);
  Serial.println("sent");
  delay(3000);
}
