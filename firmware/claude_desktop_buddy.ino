// Claude Desktop Buddy — MVP firmware (M5StickC Plus 1.1)
//
// Notify-only: a Mac daemon connects over BLE and writes prompt text to
// PROMPT_CHAR_UUID. On receipt this buzzes, blinks the LED, and shows the
// text on the LCD. Button A dismisses / shows the next queued message.
// Button B clears the whole queue. No round-trip decision is sent back to
// the Mac in this MVP — that's the V2 scope.
//
// Board: M5StickC Plus 1.1 (ESP32-PICO-D4, ST7789V2 135x240 LCD, buzzer G2,
// LED G10 active-low, buttons G37/G39, AXP192 PMIC).
//
// Libraries (install via Arduino Library Manager):
//   - M5StickCPlus   (official M5Stack library — Lcd/Beep/Axp/buttons)
//   - NimBLE-Arduino (h2zero) — lower RAM footprint than the stock ESP32 BLE
//     stack, needed on this board's 4MB-flash/no-PSRAM ESP32-PICO-D4.
//
// UUIDs must match host/daemon.py exactly.

#include <M5StickCPlus.h>
#include <NimBLEDevice.h>

static const char* SERVICE_UUID      = "58f54036-4176-47fe-890f-9f3abdadd857";
static const char* PROMPT_CHAR_UUID  = "997b42ca-70d2-47be-bb6a-9943bd41f24b";
static const char* DEVICE_NAME       = "ClaudeBuddy";

static const int LED_PIN = 10;   // active LOW on this board
static const int QUEUE_SIZE = 3; // small — no SD/PSRAM, keep it in RAM

static String messageQueue[QUEUE_SIZE];
static int queueCount = 0;
static bool showingMessage = false;

NimBLEServer* pServer = nullptr;

void ledOn()  { digitalWrite(LED_PIN, LOW); }
void ledOff() { digitalWrite(LED_PIN, HIGH); }

void alertBuzzAndBlink() {
  ledOn();
  M5.Beep.tone(4000, 120);
  delay(150);
  M5.Beep.mute();
  delay(80);
  M5.Beep.tone(4000, 120);
  delay(150);
  M5.Beep.mute();
  ledOff();
}

// Simple word-wrap for the 135x240 portrait LCD at text size 2 (~11px/char).
void renderMessage(const String& text) {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(DARKGREY, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(4, 4);

  const int charsPerLine = 12; // conservative for 135px width at size 2
  int start = 0;
  int line = 0;
  int maxLines = 9; // leave room for footer

  while (start < (int)text.length() && line < maxLines) {
    int end = min(start + charsPerLine, (int)text.length());
    // avoid splitting mid-word if a space is nearby
    if (end < (int)text.length()) {
      int lastSpace = text.lastIndexOf(' ', end);
      if (lastSpace > start) end = lastSpace;
    }
    M5.Lcd.setCursor(4, 4 + line * 18);
    M5.Lcd.print(text.substring(start, end));
    start = end;
    while (start < (int)text.length() && text[start] == ' ') start++;
    line++;
  }

  // footer: queue depth + battery
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(4, 210);
  float vbat = M5.Axp.GetBatVoltage();
  M5.Lcd.printf("q:%d  batt:%.2fV", queueCount, vbat);
}

void renderIdle() {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(DARKGREY, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 90);
  M5.Lcd.print("Claude");
  M5.Lcd.setCursor(10, 112);
  M5.Lcd.print("Buddy");
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(10, 140);
  M5.Lcd.print("waiting...");
  showingMessage = false;
}

void showNextIfAny() {
  if (queueCount > 0) {
    String msg = messageQueue[0];
    for (int i = 1; i < queueCount; i++) messageQueue[i - 1] = messageQueue[i];
    queueCount--;
    showingMessage = true;
    renderMessage(msg);
  } else {
    renderIdle();
  }
}

void enqueueMessage(const String& text) {
  if (queueCount >= QUEUE_SIZE) {
    // drop oldest to make room — MVP has no persistence anyway
    for (int i = 1; i < QUEUE_SIZE; i++) messageQueue[i - 1] = messageQueue[i];
    queueCount--;
  }
  messageQueue[queueCount++] = text;

  alertBuzzAndBlink();
  if (!showingMessage) {
    showNextIfAny();
  }
}

class PromptCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* pChar, NimBLEConnInfo& connInfo) override {
    std::string value = pChar->getValue();
    if (value.empty()) return;
    String text = String(value.c_str());
    enqueueMessage(text);
  }
};

void setupBLE() {
  NimBLEDevice::init(DEVICE_NAME);
  // Larger MTU so a full prompt line fits one write; daemon still truncates
  // to keep well under this so slower centrals that don't negotiate up
  // still work.
  NimBLEDevice::setMTU(185);

  pServer = NimBLEDevice::createServer();
  // 2.x stopped auto-restarting advertising after a disconnect; without this
  // the board goes silent the moment the daemon disconnects (even via a
  // clean exit) and only a re-upload brings it back, since setup() only
  // runs once at boot.
  pServer->advertiseOnDisconnect(true);
  NimBLEService* pService = pServer->createService(SERVICE_UUID);

  NimBLECharacteristic* pPromptChar = pService->createCharacteristic(
      PROMPT_CHAR_UUID,
      NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  pPromptChar->setCallbacks(new PromptCallbacks());

  pService->start();

  // Primary payload (31-byte legacy limit) holds the service UUID; flags +
  // a 128-bit UUID already eat 21 of those 31 bytes, leaving no room for
  // the name too, so the name has to go in the scan response packet instead.
  NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->enableScanResponse(true);
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setName(DEVICE_NAME);
  pAdvertising->start();
}

void setup() {
  M5.begin();
  M5.Lcd.setRotation(0);
  pinMode(LED_PIN, OUTPUT);
  ledOff();

  renderIdle();
  setupBLE();
}

void loop() {
  M5.update();

  if (M5.BtnA.wasPressed()) {
    showNextIfAny(); // dismiss current, show next or go idle
  }

  if (M5.BtnB.wasPressed()) {
    queueCount = 0; // clear everything
    renderIdle();
  }

  delay(20);
}
