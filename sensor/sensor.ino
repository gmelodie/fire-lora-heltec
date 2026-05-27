#include <SPI.h>
#include <RadioLib.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <SSD1306Wire.h>
#include <EEPROM.h>
#include "esp_sleep.h"
#include "esp_system.h"
#include "settings.h"

/* =========================================================
   Display
   ========================================================= */

static SSD1306Wire display(0x3c, SDA_OLED, SCL_OLED);

SX1262 radio = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY);
Adafruit_BME280 bme;

/* =========================================================
   Globals
   ========================================================= */

uint8_t sensorID = 1;
RTC_DATA_ATTR uint32_t msgCounter = 0;
RTC_DATA_ATTR uint8_t pingBackoffStep = 0;

RTC_DATA_ATTR bool gatewayFound = false;
bool waitingAck = false;

unsigned long lastTx = 0;
bool firstTx = true;
unsigned long wakeTime = 0;

bool screenOn = false;
unsigned long screenTimer = 0;

volatile bool receivedFlag = false;
int retryCount = 0;

bool bmeFound = false;

#ifndef CAMERA_BATTERY_AVAILABLE
#define CAMERA_BATTERY_AVAILABLE 0
#endif

bool cameraBatteryAvailable = (CAMERA_BATTERY_AVAILABLE == 1);

RTC_DATA_ATTR bool deployMode = false;
RTC_DATA_ATTR int8_t cachedIsV3 = -1;   // -1 = unknown, 0 = V3.2, 1 = V3
RTC_DATA_ATTR int filteredBatteryPct = -1;
RTC_DATA_ATTR int lastGoodBatteryPct = 100;
int16_t deployRSSI = 0;
unsigned long lastDeployPongTime = 0;
unsigned long lastDeployPing = 0;
unsigned long lastDeployDisplay = 0;
int cachedBattery = -1;
unsigned long lastBatteryUpdate = 0;
bool deployGwLost = false;

bool firstNormalSend = false;
String cachedTemp = "-";
String cachedHumidity = "-";
String cachedPressure = "-";
String cachedHeltecBat = "-";
unsigned long screenTimeoutMs = SCREEN_TIMEOUT;


/* =========================================================
   OLED Power
   ========================================================= */

void VextON() {
  pinMode(Vext, OUTPUT);
  digitalWrite(Vext, LOW);
}

/* =========================================================
   Display helper
   ========================================================= */

void showMessage(String l1, String l2 = "") {
  display.displayOn();
  display.clear();
  display.setTextAlignment(TEXT_ALIGN_LEFT);
  display.setFont(ArialMT_Plain_16);
  display.drawString(0, 16, l1);
  display.drawString(0, 36, l2);
  display.display();

  screenOn = true;
  screenTimer = millis();
}

void showDeployStatus() {
  if (cachedBattery < 0 || millis() - lastBatteryUpdate > 30000) {
    cachedBattery = readBattery();
    lastBatteryUpdate = millis();
  }
  bool gwInRange = (lastDeployPongTime > 0 && !deployGwLost);
  bool pingPending = lastDeployPing > 0 &&
                     (lastDeployPongTime == 0 || lastDeployPing > lastDeployPongTime) &&
                     !deployGwLost;

  String gwLine;
  if (deployGwLost)     gwLine = "GW: NO SIGNAL";
  else if (pingPending) gwLine = "GW: ---";
  else                  gwLine = "GW: IN RANGE";

  display.displayOn();
  display.clear();
  display.setFont(ArialMT_Plain_10);
  display.setTextAlignment(TEXT_ALIGN_LEFT);
  display.drawString(0, 0,  "DEPLOY  ID:" + String(sensorID));
  display.drawString(0, 14, gwLine);
  display.drawString(0, 28, "Bat: " + String(cachedBattery) + "%");
  display.drawString(0, 42, gwInRange ? "RSSI: " + String(deployRSSI) + "dBm" : "RSSI: ---");
  display.display();
}

/* =========================================================
   Battery
   ========================================================= */

// Camera battery: empirical thresholds for external 30k/10k divider, ADC_11db
int readAdcBattery(uint8_t pin) {
  int sum = 0;
  for (int i = 0; i < NUM_ADC_SAMPLES; i++) {
    sum += analogRead(pin);
    delay(5);
  }
  int raw = sum / NUM_ADC_SAMPLES;

  if (raw >= BAT_100) return 100;
  if (raw >= BAT_80) return 80;
  if (raw >= BAT_50) return 50;
  if (raw >= BAT_25) return 25;
  if (raw >= BAT_10) return 10;
  return 0;
}

int readCameraBattery() { return readAdcBattery(CAMERA_BATTERY_PIN); }

// Heltec battery circuit differs between board revisions:
//   V3:   no eFuse ADC calibration → analogReadMilliVolts returns 0; use raw analogRead.
//         ADC input loading on the 390k/100k divider gives effective ratio ~49x.
//   V3.2: eFuse calibration present → analogReadMilliVolts works; ratio ~5.03x.
// Algorithm: discard first sample (S/H bias), take N samples, median-filter to reject
// outliers, convert ONCE from median pin voltage to battery mV, interpolate OCV once,
// then IIR-smooth across calls. Avoids the noise amplification of averaging per-sample
// percentages through a non-linear interpolation.
int readBattery() {
  static const uint16_t OCV[] = {
    4190, 4120, 4050, 4020, 3990, 3940, 3890, 3845, 3800, 3760,
    3720, 3675, 3630, 3580, 3530, 3475, 3420, 3360, 3300, 3200, 3100
  };
  const int NUM_OCV = 21;
  const int N = 20;

  pinMode(ADC_CTRL_PIN, OUTPUT);
  digitalWrite(ADC_CTRL_PIN, HIGH);
  analogSetPinAttenuation(BATTERY_PIN, ADC_11db);
  delay(20);

  if (cachedIsV3 < 0) {
    int zeroes = 0;
    for (int i = 0; i < 5; i++) {
      if (analogReadMilliVolts(BATTERY_PIN) == 0) zeroes++;
      delay(2);
    }
    cachedIsV3 = (zeroes >= 3) ? 1 : 0;
  }
  bool isV3 = (cachedIsV3 == 1);

  if (isV3) analogRead(BATTERY_PIN);
  else      analogReadMilliVolts(BATTERY_PIN);
  delay(5);

  int samples[N];
  for (int i = 0; i < N; i++) {
    samples[i] = isV3
      ? (int)((float)analogRead(BATTERY_PIN) * (ADC_REF * 1000.0f) / ADC_RES)
      : (int)analogReadMilliVolts(BATTERY_PIN);
    delay(5);
  }

  for (int i = 1; i < N; i++) {
    int x = samples[i];
    int j = i - 1;
    while (j >= 0 && samples[j] > x) { samples[j + 1] = samples[j]; j--; }
    samples[j + 1] = x;
  }
  int medPinMv = samples[N / 2];

  uint32_t batMv = (uint32_t)(medPinMv * BATTERY_RATIO);

  // Plausibility clamp. A real 1S LiPo lives in 3.0–4.2 V. Anything outside that is
  // almost certainly an ADC glitch or wiring issue, and feeding it through the OCV
  // interpolation would yield 0 % or 100 % nonsense. Return the last good value.
  if (batMv < 2800 || batMv > 4400) {
    Serial.printf("Heltec bat OOR isV3=%d med_pin_mv=%d bat_mv=%lu — keeping last=%d\n",
                  isV3, medPinMv, batMv, lastGoodBatteryPct);
    return lastGoodBatteryPct;
  }

  int pct;
  if (batMv >= OCV[0]) pct = 100;
  else if (batMv <= OCV[NUM_OCV - 1]) pct = 0;
  else {
    const int PCT_STEP = 100 / (NUM_OCV - 1);
    pct = 0;
    for (int j = 0; j < NUM_OCV - 1; j++) {
      if (batMv >= OCV[j + 1]) {
        pct = (NUM_OCV - j - 2) * PCT_STEP
            + (int)((batMv - OCV[j + 1]) * PCT_STEP / (OCV[j] - OCV[j + 1]));
        break;
      }
    }
  }

  if (filteredBatteryPct < 0) filteredBatteryPct = pct;
  else                        filteredBatteryPct = (filteredBatteryPct * 3 + pct + 2) / 4;

  lastGoodBatteryPct = filteredBatteryPct;

  Serial.printf("Heltec bat isV3=%d med_pin_mv=%d bat_mv=%lu raw_pct=%d filt_pct=%d\n",
                isV3, medPinMv, batMv, pct, filteredBatteryPct);
  return filteredBatteryPct;
}

/* =========================================================
   EEPROM
   ========================================================= */

void loadSensorID() {
  EEPROM.begin(EEPROM_SIZE);
#ifdef SENSOR_ID
  sensorID = SENSOR_ID;
  saveSensorID();
#else
  sensorID = EEPROM.read(SENSOR_ID_ADDR);
  if (sensorID == 0xFF || sensorID == 0)
    sensorID = 1;
#endif
}

void saveSensorID() {
  EEPROM.write(SENSOR_ID_ADDR, sensorID);
  EEPROM.commit();
}

/* =========================================================
   Radio
   ========================================================= */

void setFlag(void) {
  receivedFlag = true;
}

bool initRadio() {
  Serial.println("Initializing radio");

  int state = radio.begin(RX_FREQ_MHZ);

  if (state != RADIOLIB_ERR_NONE) {
    Serial.print("Radio failed: ");
    Serial.println(state);
    while (true);
  }

  radio.setSpreadingFactor(RX_SF);
  radio.setBandwidth(RX_BW_KHZ);
  radio.setCodingRate(RX_CR);
  radio.setOutputPower(TX_POWER_DBM);

  radio.setDio2AsRfSwitch();
  radio.setDio1Action(setFlag);

  Serial.println("Radio ready");
  return true;
}

/* =========================================================
   Sleep
   ========================================================= */

void deepSleep(uint32_t ms) {
  display.displayOff();
  radio.sleep();
  esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000ULL);
  esp_deep_sleep_start();
}

/* =========================================================
   TX
   ========================================================= */

void transmit(String msg) {
  Serial.println("TX: " + msg);
  showMessage("Sending", msg);

  int state = radio.transmit(msg);

  if (state != RADIOLIB_ERR_NONE) {
    Serial.print("TX error: ");
    Serial.println(state);
  }
  receivedFlag = false;
  radio.startReceive();
  delay(100);
}

void sendPing() {
  String msg = "PING|" + String(sensorID);
  transmit(msg);
}


void sendSensorData() {
  String temperature = "nil";
  String humidity = "nil";
  String pressure = "nil";
  String cameraBattery = "nil";

  if (bmeFound) {
    bme.takeForcedMeasurement();
    temperature = String(bme.readTemperature(), 2);
    humidity = String(bme.readHumidity(), 2);
    pressure = String(bme.readPressure() / 100.0F, 2);
  }

  String heltecBattery = String(readBattery());
  cachedTemp = temperature;
  cachedHumidity = humidity;
  cachedPressure = pressure;
  cachedHeltecBat = heltecBattery;

  if (cameraBatteryAvailable) {
    cameraBattery = String(readCameraBattery());
  }

  String msg =
    "DATA|" +
    String(sensorID) + "|" +
    temperature + "|" +
    humidity + "|" +
    pressure + "|" +
    heltecBattery + "|" +
    cameraBattery + "|" +
    String(msgCounter);

  waitingAck = true;
  retryCount = 0;

  transmit(msg);
}

/* =========================================================
   RX
   ========================================================= */

void processPacket(String msg, int16_t rssi) {
  Serial.println("RX: " + msg);

  if (msg.startsWith("PONG")) {
    gatewayFound = true;
    if (deployMode) {
      deployRSSI = rssi;
      lastDeployPongTime = millis();
      deployGwLost = false;
    } else {
      showMessage("Gateway", "Connected");
    }
    return;
  }

  if (msg.startsWith("ACK")) {
    waitingAck = false;
    retryCount = 0;
    msgCounter++;
    if (!deployMode) {
      if (firstNormalSend) {
        firstNormalSend = false;
        screenTimeoutMs = 5000;
        display.displayOn();
        display.clear();
        display.setFont(ArialMT_Plain_10);
        display.setTextAlignment(TEXT_ALIGN_LEFT);
        display.drawString(0,  0, "SENT OK   Bat:" + cachedHeltecBat + "%");
        display.drawString(0, 16, "T: " + cachedTemp + " C");
        display.drawString(0, 32, "H: " + cachedHumidity + " %");
        display.drawString(0, 48, "P: " + cachedPressure + " hPa");
        display.display();
        screenOn = true;
        screenTimer = millis();
      } else {
        showMessage("ACK", "OK");
      }
    }
    return;
  }
  Serial.println();
}

void handleReceive() {
  if (!receivedFlag) return;

  receivedFlag = false;

  String msg;
  int state = radio.readData(msg);

  if (state == RADIOLIB_ERR_NONE && msg.length() > 0) {
    int16_t rssi = radio.getRSSI();
    processPacket(msg, rssi);
  }

  radio.startReceive();
}

/* =========================================================
   Button
   ========================================================= */

void handleButton() {
  static bool lastState = HIGH;
  static unsigned long pressStart = 0;

  bool current = digitalRead(BUTTON_PIN);

  if (lastState == HIGH && current == LOW) {
    pressStart = millis();
  }

  if (lastState == LOW && current == HIGH) {
    unsigned long held = millis() - pressStart;

    if (held < 50) {
      // ignore (bounce)
    } else if (held < 1000) {
      // short press: toggle deploy mode
      deployMode = !deployMode;
      if (deployMode) {
        lastDeployPongTime = 0;
        deployRSSI = 0;
        lastDeployPing = 0;
        lastDeployDisplay = millis();
        cachedBattery = -1;
        deployGwLost = false;
        showMessage("Deploy Mode", "ON");
      } else {
        pingBackoffStep = 0;
        lastTx = 0;
        firstNormalSend = true;
        showMessage("Deploy Mode", "OFF");
      }
    } else {
      // long press: cycle sensor ID
      sensorID++;
      if (sensorID > MAX_SENSORS) sensorID = 1;
      saveSensorID();
      showMessage("Sensor ID", String(sensorID));
    }
  }

  lastState = current;
}

/* =========================================================
   Setup
   ========================================================= */

void setup() {
  Serial.begin(115200);
  delay(1000);

  bool coldBoot = (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER);

  VextON();
  delay(100);

  pinMode(RST_OLED, OUTPUT);
  digitalWrite(RST_OLED, LOW);
  delay(20);
  digitalWrite(RST_OLED, HIGH);

  display.init();
  display.setFont(ArialMT_Plain_10);

  if (coldBoot) {
    showMessage("Sensor Boot", "V3");
  }

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  analogReadResolution(12);

  pinMode(ADC_CTRL_PIN, OUTPUT);
  digitalWrite(ADC_CTRL_PIN, HIGH);
  // Must be set explicitly; default attenuation varies between ESP32-S3 silicon revisions
  analogSetPinAttenuation(BATTERY_PIN, ADC_11db);

  if (cameraBatteryAvailable) {
    pinMode(CAMERA_BATTERY_PIN, INPUT);
    analogSetPinAttenuation(CAMERA_BATTERY_PIN, ADC_11db);
  }

  loadSensorID();

  if (coldBoot) {
    deployMode = true;
    lastDeployPongTime = 0;
    deployRSSI = 0;
    lastDeployPing = 0;
    cachedBattery = -1;
    deployGwLost = false;
  }

  Wire1.begin(BME_SDA, BME_SCL);
  bmeFound = bme.begin(0x76, &Wire1);

  if (bmeFound) {
    bme.setSampling(Adafruit_BME280::MODE_FORCED,
                    Adafruit_BME280::SAMPLING_X1,
                    Adafruit_BME280::SAMPLING_X1,
                    Adafruit_BME280::SAMPLING_X1,
                    Adafruit_BME280::FILTER_OFF);
    Serial.println("BME280 OK");
    if (coldBoot) showMessage("BME280", "Detected");
  } else {
    Serial.println("BME280 not found");
    if (coldBoot) showMessage("BME280", "Missing");
  }

  if (coldBoot) {
    display.clear();
    display.drawString(0, 0, "Sensor Boot V3");
    display.drawString(0, 16, bmeFound ? "BME: OK" : "BME: MISSING");
    display.display();
    delay(1500);

    showMessage("Heltec Batt", String(readBattery()) + "%");
    delay(1500);

    if (cameraBatteryAvailable) {
      showMessage("Cam Batt", String(readCameraBattery()) + "%");
      delay(1500);
    }
  }

  initRadio();
  radio.startReceive();

  lastTx = millis();
  wakeTime = millis();
}

/* =========================================================
   Loop
   ========================================================= */

void loop() {
  handleReceive();
  handleButton();

  if (deployMode) {
    if (millis() - lastDeployDisplay >= 1000) {
      showDeployStatus();
      lastDeployDisplay = millis();
    }
    if (!deployGwLost && lastDeployPing > 0 &&
        millis() - lastDeployPing > 2000 &&
        (lastDeployPongTime == 0 || lastDeployPing > lastDeployPongTime)) {
      deployGwLost = true;
    }

    if (lastDeployPing == 0 || millis() - lastDeployPing >= DEPLOY_PING_INTERVAL_MS) {
      String pingMsg = "PING|" + String(sensorID);
      Serial.println("DEPLOY TX: " + pingMsg);
      radio.transmit(pingMsg);
      receivedFlag = false;
      radio.startReceive();
      lastDeployPing = millis();
    }
    return;
  }

  if (screenOn && millis() - screenTimer > screenTimeoutMs) {
    display.clear();
    display.display();
    display.displayOff();
    screenOn = false;
    screenTimeoutMs = SCREEN_TIMEOUT;
  }

  if (!gatewayFound) {
    if (millis() - lastTx >= PING_INTERVAL_MS) {
      sendPing();
      lastTx = millis();
    }
    if (millis() > GATEWAY_SEARCH_MS) {
      uint8_t step = min(pingBackoffStep, (uint8_t)MAX_BACKOFF_STEP);
      uint32_t backoffMs = min(BACKOFF_BASE_MS << step, BACKOFF_MAX_MS);
      pingBackoffStep = step + 1;
      Serial.printf("Gateway not found, sleeping %lu s (step %u)\n", backoffMs / 1000, step);
      deepSleep(backoffMs);
    }
    return;
  }
  pingBackoffStep = 0;

  if (!waitingAck && firstTx) {
    firstTx = false;
    lastTx = millis();
    sendSensorData();
  }

  if (waitingAck && millis() - lastTx > ACK_TIMEOUT) {
    if (retryCount < MAX_RETRIES) {
      retryCount++;
      Serial.println("Retrying TX...");
      sendSensorData();
      lastTx = millis();
    } else {
      Serial.println("ACK failed");
      waitingAck = false;
    }
  }

  if (gatewayFound && !waitingAck && !firstTx) {
    if (screenOn) return;
    Serial.printf("AWAKE_S:%lu\n", (millis() - wakeTime) / 1000);
    deepSleep(TX_INTERVAL);
  }
}
