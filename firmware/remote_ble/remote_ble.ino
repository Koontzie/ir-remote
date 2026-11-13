/*
 * BLE GATT + programmable IR slots — XIAO ESP32-C3 (rev 2 board)
 *
 * Keeps Phase 1's IR send path (GPIO4, IRremoteESP8266) and adds a BLE GATT
 * service so a Web Bluetooth app can program and fire five IR slots.
 * Slot config persists in NVS via Preferences, so it survives a power cycle.
 *
 * GATT — service b457c32b-22b1-425f-8a88-4d6dc37ba4eb, device name "IR-Remote":
 *   config  (WRITE)  {"slot":1,"proto":"SAMSUNG","code":"0xE0E040BF","bits":32}
 *   trigger (WRITE)  {"slot":1}                        fire a stored slot, or
 *                    {"proto":"NEC","code":"0x...","bits":32}  direct send (no
 *                    slot round-trip) — used by the Identify sweep.
 *   status  (NOTIFY) "saved:1" / "sent:1" / "sent:direct" / "err:..."
 *
 * Protocols: NEC, SAMSUNG, SONY, RC5, RC6 (all native to IRremoteESP8266).
 * Phase 5 Sitting B: larger MTU + relaxed connection params (6s supervision
 * timeout) to stop the reason-520 link drops during sustained sweep writes.
 *
 * Phase 3 hardware — NPN driver stage off the 5V rail, ~64mA through two IR
 * LEDs in series (was ~13mA on direct GPIO drive, inches of range; now 20-30ft):
 *   5V --33R--> LED1(+)-(-) --> LED2(+)-(-) --> COLLECTOR
 *   GPIO4 --1k--> BASE           EMITTER --> GND
 *
 * Buttons: INPUT_PULLUP, wired pin -> button -> GND, so pressed reads LOW.
 * Fixed mapping, button N -> slot N. Buttons work with no BLE client
 * connected — the remote is standalone.
 *
 * Rev 2 hardware (2026-08-09) — Seeed XIAO ESP32-C3, battery + boost, power
 * gated by a physical switch on the boost's EN pin. NO deep sleep, NO wake
 * pins — the switch IS the power management. Pin map (see
 * hardware/DESIGN-c3-board.md): buttons GPIO3/5/6 (XIAO D1/D3/D4), IR base
 * GPIO4 (D2), button LED rings GPIO7/21/20 (D5/D6/D7).
 * GPIO2/8/9 (D0/D8/D9) are C3 strapping pins — never assign them.
 *
 * LED signal module (2026-08-10) — non-blocking millis()-based state machine
 * (ledInit / ledTick / ledSignal) drives the three rings over LEDC PWM with the
 * feedback vocabulary in hardware/DESIGN-c3-board.md: boot cascade, steady idle,
 * press flash, sent double-pulse, empty-slot blink, connect breathe, sweep chase.
 * Idle brightness is the single constant kRingIdleDuty.
 */

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <IRremoteESP8266.h>
#include <IRsend.h>

// ── UUIDs (generated once, hardcoded — the web app must match these) ─────────
#define SERVICE_UUID "b457c32b-22b1-425f-8a88-4d6dc37ba4eb"
#define CONFIG_UUID  "d997012d-7d2b-47de-ae87-bae14df446ef"
#define TRIGGER_UUID "58397514-04a3-4265-9590-9d910c4e99d2"
#define STATUS_UUID  "b8ddfe01-519f-430d-bd4e-aba0dd852e2c"

static const uint16_t kIrLedPin   = 4;
static const uint8_t  kMinSlot    = 1;
static const uint8_t  kMaxSlot    = 5;
static const char*    kDevName    = "IR-Remote";
static const uint32_t kDebounceMs = 30;

// Button N -> slot N, fixed mapping. Pressed = LOW (INPUT_PULLUP to GND).
struct ButtonState {
  uint8_t  pin;
  uint8_t  slot;
  int      stable;        // debounced level; HIGH = released
  int      lastRead;
  uint32_t lastChangeMs;
};

// XIAO C3 rev-2 map (2026-08-09): buttons on GPIO3/5/6 = XIAO D1/D3/D4.
// GPIO0/1 are not broken out on the XIAO; GPIO2/8/9 are strapping pins.
// No RTC-wake constraint anymore — power is gated by the physical switch.
static ButtonState buttons[] = {
  { 3, 1, HIGH, HIGH, 0 },
  { 5, 2, HIGH, HIGH, 0 },
  { 6, 3, HIGH, HIGH, 0 },
};

// Button LED rings (low-side 2N2222 drivers). Reserved here so nothing else
// claims the pins; the ledSignal() pattern module is still to be written.
static const uint8_t kRingPins[3] = { 7, 21, 20 };  // XIAO D5/D6/D7
static const size_t kNumButtons = sizeof(buttons) / sizeof(buttons[0]);

IRsend      irsend(kIrLedPin);
Preferences prefs;

NimBLECharacteristic* statusChar = nullptr;
static bool clientConnected = false;

// IR sends block for ~70ms and drive the RMT peripheral. Doing that inside a
// NimBLE callback runs it on the host task's limited stack, so trigger writes
// only set this flag and loop() does the actual send.
static volatile uint8_t pendingSlot = 0;

// A direct send (Identify sweep) carries its own proto/code/bits, no slot. The
// BLE callback stages it here; loop() performs the blocking IR send. Write the
// scalars first and the flag LAST — loop() checks the flag first, so it never
// acts on a half-written record.
static volatile bool pendingDirect = false;
static char     directProto[12] = {0};
static uint64_t directCode = 0;
static uint16_t directBits = 32;

// ── LED signal module ────────────────────────────────────────────────────────
// Non-blocking feedback on the three blue button rings. Low-side 2N2222 drivers
// (pin HIGH = ring lit), driven by LEDC PWM so brightness ramps and breathing
// are possible, not just on/off.
//
// The whole module is a millis()-based state machine ticked from loop() via
// ledTick(). There is no delay() and nothing blocks — every phase is computed
// from *elapsed time* (now - t0), never counted per tick, so when the ~70ms
// 38kHz IR send steals loop() the next tick simply resumes at the correct point
// instead of stalling. ledSignal() only records an event; ledTick() renders it.
//
// This block is placed before the first function on purpose: the LedEvent enum
// must precede the auto-generated prototypes that reference it.

enum LedEvent {
  LED_BOOT,        // whole board: power-up cascade, then idle
  LED_PRESSED,     // one ring:  snap to 100% for ~80ms, then idle
  LED_SENT,        // one ring:  double-pulse at 100% after a send completes
  LED_EMPTY,       // one ring:  three fast blinks (empty slot)
  LED_CONNECTED,   // whole board: one slow breathe
  LED_SWEEP,       // whole board: chase; refreshed per direct send, self-times-out
};

// Idle ring brightness lives here and nowhere else — the one knob to dim.
static const uint8_t  kRingIdleDuty = 64;     // ~25% of 255
static const uint8_t  kRingFullDuty = 255;    // 100%
static const uint8_t  kRingOffDuty  = 0;
static const uint32_t kRingPwmFreq  = 5000;   // Hz — flicker-free
static const uint8_t  kRingPwmBits  = 8;      // 0..255 duty

static const uint32_t kBootStepMs   = 150;    // per-ring cascade slot
static const uint32_t kPressMs      = 80;     // press flash
static const uint32_t kSentHalfMs   = 60;     // one half of the sent double-pulse
static const uint32_t kEmptyHalfMs  = 60;     // one half of an empty-slot blink
static const uint32_t kBreatheMs    = 1200;   // one up/down breathe
static const uint32_t kChaseStepMs  = 130;    // per-ring dwell during a sweep chase
static const uint32_t kSweepHoldMs  = 500;    // no direct send this long => chase ends

enum BoardAnim { BOARD_NONE, BOARD_BOOT, BOARD_BREATHE, BOARD_CHASE };
enum RingAnim  { RING_IDLE, RING_PRESS, RING_SENT, RING_EMPTY };

static BoardAnim boardAnim = BOARD_NONE;
static uint32_t  boardT0   = 0;
static uint32_t  chaseSeen = 0;                 // last LED_SWEEP refresh
static RingAnim  ringAnim[3] = { RING_IDLE, RING_IDLE, RING_IDLE };
static uint32_t  ringT0[3]   = { 0, 0, 0 };
static uint8_t   lastDuty[3] = { 1, 1, 1 };     // impossible duty => force first write

void ledInit() {
  for (uint8_t i = 0; i < 3; i++) {
    if (!ledcAttach(kRingPins[i], kRingPwmFreq, kRingPwmBits))
      Serial.printf("[led] WARN ledcAttach failed on GPIO%u\n", kRingPins[i]);
    ledcWrite(kRingPins[i], kRingOffDuty);      // dark until the boot cascade
    lastDuty[i] = kRingOffDuty;
    ringAnim[i] = RING_IDLE;
  }
  Serial.println("[led] ring PWM ready (dark until boot cascade)");
}

// A single ring's duty when no whole-board animation owns the display.
static uint8_t ringDuty(uint8_t i, uint32_t now) {
  const uint32_t e = now - ringT0[i];
  switch (ringAnim[i]) {
    case RING_PRESS:
      if (e >= kPressMs) { ringAnim[i] = RING_IDLE; return kRingIdleDuty; }
      return kRingFullDuty;
    case RING_SENT:                              // full, idle, full, idle
      if (e >= 4 * kSentHalfMs) { ringAnim[i] = RING_IDLE; return kRingIdleDuty; }
      return ((e / kSentHalfMs) & 1) ? kRingIdleDuty : kRingFullDuty;
    case RING_EMPTY:                             // full/off ×3 — harder than SENT
      if (e >= 6 * kEmptyHalfMs) { ringAnim[i] = RING_IDLE; return kRingIdleDuty; }
      return ((e / kEmptyHalfMs) & 1) ? kRingOffDuty : kRingFullDuty;
    default:
      return kRingIdleDuty;
  }
}

// Triangle breathe idle->full->idle over kBreatheMs; never dips below idle.
static uint8_t breatheDuty(uint32_t e) {
  const uint32_t half = kBreatheMs / 2;
  uint32_t v = (e < half) ? (e * 255) / half
                          : ((kBreatheMs - e) * 255) / half;
  return (v < kRingIdleDuty) ? kRingIdleDuty : (uint8_t)v;
}

void ledTick() {
  const uint32_t now = millis();
  uint8_t duty[3];

  if (boardAnim == BOARD_CHASE && (now - chaseSeen) > kSweepHoldMs)
    boardAnim = BOARD_NONE;                      // sweep went quiet -> idle

  switch (boardAnim) {
    case BOARD_BOOT: {
      const uint32_t active = (now - boardT0) / kBootStepMs;   // 0,1,2, then done
      if (active >= 3) {
        boardAnim = BOARD_NONE;
        for (uint8_t i = 0; i < 3; i++) duty[i] = kRingIdleDuty;
      } else {
        for (uint8_t i = 0; i < 3; i++)
          duty[i] = (i == active) ? kRingFullDuty : kRingOffDuty;
      }
      break;
    }
    case BOARD_BREATHE: {
      const uint32_t e = now - boardT0;
      if (e >= kBreatheMs) {
        boardAnim = BOARD_NONE;
        for (uint8_t i = 0; i < 3; i++) duty[i] = kRingIdleDuty;
      } else {
        const uint8_t b = breatheDuty(e);
        for (uint8_t i = 0; i < 3; i++) duty[i] = b;
      }
      break;
    }
    case BOARD_CHASE: {
      const uint8_t lit = ((now - boardT0) / kChaseStepMs) % 3;
      for (uint8_t i = 0; i < 3; i++)
        duty[i] = (i == lit) ? kRingFullDuty : kRingIdleDuty;
      break;
    }
    default:                                     // BOARD_NONE: per-ring or idle
      for (uint8_t i = 0; i < 3; i++) duty[i] = ringDuty(i, now);
      break;
  }

  for (uint8_t i = 0; i < 3; i++) {
    if (duty[i] != lastDuty[i]) {                // only write on change
      ledcWrite(kRingPins[i], duty[i]);
      lastDuty[i] = duty[i];
    }
  }
}

// Record an event. buttonIndex is 0-based (ring index); ignored for whole-board
// events. Per-ring events out of range are dropped rather than clamped.
void ledSignal(LedEvent event, uint8_t buttonIndex) {
  const uint32_t now = millis();
  switch (event) {
    case LED_BOOT:      boardAnim = BOARD_BOOT;    boardT0 = now; break;
    case LED_CONNECTED: boardAnim = BOARD_BREATHE; boardT0 = now; break;
    case LED_SWEEP:
      if (boardAnim != BOARD_CHASE) { boardAnim = BOARD_CHASE; boardT0 = now; }
      chaseSeen = now;                            // keep the chase alive
      break;
    case LED_PRESSED:
      if (buttonIndex < 3) { ringAnim[buttonIndex] = RING_PRESS; ringT0[buttonIndex] = now; }
      break;
    case LED_SENT:
      if (buttonIndex < 3) { ringAnim[buttonIndex] = RING_SENT;  ringT0[buttonIndex] = now; }
      break;
    case LED_EMPTY:
      if (buttonIndex < 3) { ringAnim[buttonIndex] = RING_EMPTY; ringT0[buttonIndex] = now; }
      break;
  }
}

// ── status helper ───────────────────────────────────────────────────────────
void pushStatus(const String& msg) {
  Serial.print("[status] ");
  Serial.println(msg);
  if (statusChar) {
    statusChar->setValue(msg.c_str());
    if (clientConnected) statusChar->notify();
  }
}

// ── NVS layout: per slot, keys "p<N>" proto, "c<N>" code, "b<N>" bits ────────
static String keyFor(char prefix, uint8_t slot) {
  return String(prefix) + String(slot);
}

bool slotConfigured(uint8_t slot) {
  return prefs.isKey(keyFor('p', slot).c_str());
}

void saveSlot(uint8_t slot, const String& proto, uint64_t code, uint16_t bits) {
  prefs.putString(keyFor('p', slot).c_str(), proto);
  prefs.putULong64(keyFor('c', slot).c_str(), code);
  prefs.putUShort(keyFor('b', slot).c_str(), bits);
}

// ── IR ──────────────────────────────────────────────────────────────────────
bool protoSupported(const String& p) {
  return p == "NEC" || p == "SAMSUNG" || p == "SONY" ||
         p == "RC5" || p == "RC6";
}

bool sendIr(const String& proto, uint64_t code, uint16_t bits) {
  if (proto == "NEC")      { irsend.sendNEC(code, bits);            return true; }
  if (proto == "SAMSUNG")  { irsend.sendSAMSUNG(code, bits);        return true; }
  if (proto == "SONY")     { irsend.sendSony(code, bits, 2);        return true; }
  if (proto == "RC5")      { irsend.sendRC5(code, bits);            return true; }
  if (proto == "RC6")      { irsend.sendRC6(code, bits);            return true; }
  return false;  // Sony wants >=2 repeats to be accepted by most sets
}

// Parse "0xE0E040BF" / bare hex "E0E040BF" / decimal into a code. Shared by the
// config (save) and trigger (direct send) write paths.
bool parseCode(String codeStr, uint64_t& out) {
  codeStr.trim();
  if (codeStr.isEmpty()) return false;
  char* end = nullptr;
  out = strtoull(codeStr.c_str(), &end, 0);   // base 0: handles the 0x prefix
  if (end != codeStr.c_str() && *end == '\0') return true;
  end = nullptr;
  out = strtoull(codeStr.c_str(), &end, 16);  // retry as bare hex
  return end != codeStr.c_str() && *end == '\0';
}

// ── shared send path (BLE trigger and button presses both land here) ────────
void fireSlot(uint8_t slot) {
  String   proto = prefs.getString(keyFor('p', slot).c_str());
  uint64_t code  = prefs.getULong64(keyFor('c', slot).c_str());
  uint16_t bits  = prefs.getUShort(keyFor('b', slot).c_str());

  Serial.printf("[ir] slot %u -> %s 0x%llX (%u bits)\n",
                slot, proto.c_str(), (unsigned long long)code, bits);

  if (sendIr(proto, code, bits)) {
    pushStatus(String("sent:") + slot);
    if (slot >= 1 && slot <= 3) ledSignal(LED_SENT, (uint8_t)(slot - 1));
  } else {
    pushStatus(String("err:unknown proto ") + proto);
  }
}

// ── buttons ─────────────────────────────────────────────────────────────────
// Fires on the press edge only, so holding a button does not repeat.
void pollButtons() {
  const uint32_t now = millis();

  for (size_t i = 0; i < kNumButtons; i++) {
    ButtonState& b = buttons[i];
    const int level = digitalRead(b.pin);

    if (level != b.lastRead) {          // still bouncing — restart the timer
      b.lastRead = level;
      b.lastChangeMs = now;
      continue;
    }
    if (now - b.lastChangeMs < kDebounceMs) continue;   // not settled yet
    if (level == b.stable) continue;                    // no edge

    b.stable = level;
    if (level != LOW) continue;         // release edge — ignore

    Serial.printf("[btn] GPIO%u pressed -> slot %u\n", b.pin, b.slot);
    pushStatus(String("pressed:") + b.slot);
    ledSignal(LED_PRESSED, (uint8_t)i);

    if (!slotConfigured(b.slot)) {
      Serial.printf("[btn] slot %u is empty — nothing to send\n", b.slot);
      pushStatus(String("err:empty:") + b.slot);
      ledSignal(LED_EMPTY, (uint8_t)i);
      continue;
    }
    fireSlot(b.slot);
  }
}

// ── config characteristic ───────────────────────────────────────────────────
class ConfigCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& connInfo) override {
    String raw = String(c->getValue().c_str());
    Serial.print("[ble] config write: ");
    Serial.println(raw);

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, raw);
    if (err) { pushStatus(String("err:bad json (") + err.c_str() + ")"); return; }

    int slot = doc["slot"] | 0;
    if (slot < kMinSlot || slot > kMaxSlot) {
      pushStatus("err:slot must be 1-5"); return;
    }

    String proto = String((const char*)(doc["proto"] | ""));
    proto.toUpperCase();
    if (!protoSupported(proto)) {
      pushStatus("err:proto must be NEC|SAMSUNG|SONY"); return;
    }

    uint64_t code = 0;
    if (!parseCode(String((const char*)(doc["code"] | "")), code)) {
      pushStatus("err:bad code"); return;
    }

    int bits = doc["bits"] | 32;
    if (bits <= 0 || bits > 64) { pushStatus("err:bits must be 1-64"); return; }

    saveSlot(slot, proto, code, bits);
    Serial.printf("[nvs] slot %d <- %s 0x%llX (%d bits)\n",
                  slot, proto.c_str(), (unsigned long long)code, bits);
    pushStatus(String("saved:") + slot);
  }
};

// ── trigger characteristic ──────────────────────────────────────────────────
class TriggerCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& connInfo) override {
    String raw = String(c->getValue().c_str());
    Serial.print("[ble] trigger write: ");
    Serial.println(raw);

    JsonDocument doc;
    if (deserializeJson(doc, raw)) { pushStatus("err:bad json"); return; }

    // Direct send: {"proto","code","bits"} with no slot — used by the Identify
    // sweep so it never has to round-trip through a slot. Distinguished by a
    // "code" field (slot triggers only carry "slot").
    if (doc["code"].is<const char*>()) {
      String proto = String((const char*)(doc["proto"] | ""));
      proto.toUpperCase();
      if (!protoSupported(proto)) {
        pushStatus("err:proto must be NEC|SAMSUNG|SONY|RC5|RC6"); return;
      }
      uint64_t code = 0;
      if (!parseCode(String((const char*)(doc["code"] | "")), code)) {
        pushStatus("err:bad code"); return;
      }
      int bits = doc["bits"] | 32;
      if (bits <= 0 || bits > 64) { pushStatus("err:bits must be 1-64"); return; }

      strncpy(directProto, proto.c_str(), sizeof(directProto) - 1);
      directProto[sizeof(directProto) - 1] = '\0';
      directCode = code;
      directBits = (uint16_t)bits;
      pendingDirect = true;         // flag set LAST; loop() does the send
      return;
    }

    int slot = doc["slot"] | 0;
    if (slot < kMinSlot || slot > kMaxSlot) {
      pushStatus("err:slot must be 1-5"); return;
    }
    if (!slotConfigured(slot)) {
      pushStatus(String("err:slot ") + slot + " empty"); return;
    }
    pendingSlot = (uint8_t)slot;  // loop() performs the send
  }
};

// ── server callbacks ────────────────────────────────────────────────────────
class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s, NimBLEConnInfo& connInfo) override {
    clientConnected = true;
    Serial.println("[ble] client connected");
    ledSignal(LED_CONNECTED, 0);
    // Relax the link so a brief RF hiccup — or a ~109ms blocking IR send during
    // an Identify sweep — doesn't trip the supervision timeout (the reason-520 /
    // HCI 0x208 drops seen 2026-07-26). Interval 30-60ms, no latency, 6s
    // supervision timeout. The central may renegotiate; this is a request.
    s->updateConnParams(connInfo.getConnHandle(), 24, 48, 0, 600);
  }
  void onDisconnect(NimBLEServer* s, NimBLEConnInfo& connInfo, int reason) override {
    clientConnected = false;
    Serial.printf("[ble] client disconnected (reason %d), advertising again\n", reason);
    NimBLEDevice::startAdvertising();
  }
};

void setup() {
  Serial.begin(115200);
  delay(2000);                       // let USB CDC enumerate before logging
  Serial.println();
  Serial.println("=== IR-Remote Phase 3 — BLE GATT + IR + buttons ===");

  irsend.begin();
  prefs.begin("irremote", false);

  for (size_t i = 0; i < kNumButtons; i++) {
    pinMode(buttons[i].pin, INPUT_PULLUP);
    Serial.printf("[btn] GPIO%u -> slot %u (INPUT_PULLUP, pressed = LOW)\n",
                  buttons[i].pin, buttons[i].slot);
  }

  // Ring LEDs: attach LEDC PWM and start dark. The boot cascade at the end of
  // setup() lights them; ledTick() in loop() animates them thereafter.
  ledInit();

  // Seed slot 1 with the Samsung power code proven in Phase 1, first boot only.
  if (!slotConfigured(1)) {
    saveSlot(1, "SAMSUNG", 0xE0E040BFULL, 32);
    Serial.println("[nvs] seeded slot 1 = SAMSUNG 0xE0E040BF (32 bits)");
  }

  NimBLEDevice::init(kDevName);
  // Request a larger ATT MTU: small writes benefit, and it's a prerequisite for
  // the deferred RAW chunked-write path. Web Bluetooth caps writes at 512.
  NimBLEDevice::setMTU(517);
  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  NimBLEService* service = server->createService(SERVICE_UUID);

  NimBLECharacteristic* configChar =
      service->createCharacteristic(CONFIG_UUID, NIMBLE_PROPERTY::WRITE);
  configChar->setCallbacks(new ConfigCallbacks());

  NimBLECharacteristic* triggerChar =
      service->createCharacteristic(TRIGGER_UUID, NIMBLE_PROPERTY::WRITE);
  triggerChar->setCallbacks(new TriggerCallbacks());

  statusChar = service->createCharacteristic(
      STATUS_UUID, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  statusChar->setValue("ready");

  service->start();

  // The advertising payload is 31 bytes and a 128-bit service UUID eats 18 of
  // them (+3 flags), leaving no room for an 11-byte name field — the name would
  // be silently dropped or truncated, so a name-based scan filter never matches.
  // Keep the UUID in the advertisement and put the name in the scan response,
  // which gets its own 31 bytes.
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();

  NimBLEAdvertisementData advData;
  advData.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  advData.addServiceUUID(SERVICE_UUID);
  adv->setAdvertisementData(advData);

  NimBLEAdvertisementData scanData;
  scanData.setName(kDevName);
  adv->setScanResponseData(scanData);
  adv->enableScanResponse(true);

  NimBLEDevice::startAdvertising();

  Serial.printf("[ble] advertising as \"%s\"\n", kDevName);
  Serial.printf("[ble] service %s\n", SERVICE_UUID);
  Serial.println("[ble] ready — waiting for a client");

  // Show what's already stored, so the serial log alone explains the state.
  for (uint8_t s = kMinSlot; s <= kMaxSlot; s++) {
    if (!slotConfigured(s)) continue;
    Serial.printf("[nvs] slot %d = %s 0x%llX (%u bits)\n", s,
                  prefs.getString(keyFor('p', s).c_str()).c_str(),
                  (unsigned long long)prefs.getULong64(keyFor('c', s).c_str()),
                  prefs.getUShort(keyFor('b', s).c_str()));
  }

  // Rings come alive: cascade LED1->2->3, then settle to idle.
  ledSignal(LED_BOOT, 0);
}

void loop() {
  ledTick();   // render the LED state machine every pass; must never block

  uint8_t slot = pendingSlot;
  if (slot) {
    pendingSlot = 0;
    fireSlot(slot);
  }

  if (pendingDirect) {
    // Copy out, then clear the flag, so a new direct write can stage while the
    // (blocking) send runs.
    char     proto[sizeof(directProto)];
    strncpy(proto, directProto, sizeof(proto));
    proto[sizeof(proto) - 1] = '\0';
    uint64_t code = directCode;
    uint16_t bits = directBits;
    pendingDirect = false;

    Serial.printf("[ir] direct -> %s 0x%llX (%u bits)\n",
                  proto, (unsigned long long)code, bits);
    if (sendIr(String(proto), code, bits)) pushStatus("sent:direct");
    else pushStatus(String("err:unknown proto ") + proto);
    ledSignal(LED_SWEEP, 0);   // Identify sweep -> chase; refreshes the keep-alive
  }

  pollButtons();
  delay(5);   // 5ms poll is well inside the 30ms debounce window
}
