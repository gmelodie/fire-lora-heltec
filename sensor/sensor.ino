#include <SPI.h>
#include <RadioLib.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <SSD1306Wire.h>
#include <EEPROM.h>
#include "esp_sleep.h"
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

// Heltec battery circuit differs between board revisions (detected via ESP32-S3 chip revision):
//   V3  (rev 0, ROM esp32s3-20210327): no eFuse ADC calibration, so analogReadMilliVolts
//       returns 0 — use raw analogRead instead. ADC input loading on the high-impedance
//       390k/100k divider produces ~10x attenuation, so effective ratio is 49x not 4.9x.
//   V3.2 (rev 1+): eFuse calibration present, analogReadMilliVolts works; standard 4.9x ratio.
// Both boards use ADC_CTRL HIGH to enable the voltage divider.
int readBattery() {
  static const uint16_t OCV[] = {4190, 4050, 3990, 3890, 3800, 3720, 3630, 3530, 3420, 3300, 3100};
  const int NUM_OCV = 11;

  bool isV3 = (ESP.getChipRevision() == 0);

  pinMode(ADC_CTRL_PIN, OUTPUT);
  digitalWrite(ADC_CTRL_PIN, HIGH);
  analogSetPinAttenuation(BATTERY_PIN, ADC_11db);
  delay(5);

  int samples[NUM_ADC_SAMPLES];
  for (int i = 0; i < NUM_ADC_SAMPLES; i++) {
    if (isV3)
      samples[i] = (int)((float)analogRead(BATTERY_PIN) * (ADC_REF * 1000.0f) / ADC_RES);
    else
      samples[i] = (int)analogReadMilliVolts(BATTERY_PIN);
    delay(10);
  }

  int avgPinMv = 0;
  for (int i = 0; i < NUM_ADC_SAMPLES; i++) avgPinMv += samples[i];
  avgPinMv /= NUM_ADC_SAMPLES;

  float ratio = BATTERY_RATIO;
  uint32_t avgMv = (uint32_t)(avgPinMv * ratio);
  while (avgMv > 10000 && ratio >= 1.0f) { ratio /= 10.0f; avgMv /= 10; }
  while (avgMv < 2000 && avgMv > 0)      { ratio *= 10.0f; avgMv *= 10; }

  int pctSum = 0;
  for (int i = 0; i < NUM_ADC_SAMPLES; i++) {
    uint32_t mv = (uint32_t)(samples[i] * ratio);
    int pct;
    if (mv >= OCV[0]) pct = 100;
    else if (mv <= OCV[NUM_OCV - 1]) pct = 0;
    else {
      pct = 0;
      for (int j = 0; j < NUM_OCV - 1; j++) {
        if (mv >= OCV[j + 1]) {
          pct = (10 - j - 1) * 10 + (mv - OCV[j + 1]) * 10 / (OCV[j] - OCV[j + 1]);
          break;
        }
      }
    }
    pctSum += pct;
  }

  int pct = pctSum / NUM_ADC_SAMPLES;
  Serial.printf("Heltec bat chip_rev=%d pin_mv=%d bat_mv=%lu pct=%d%%\n", ESP.getChipRevision(), avgPinMv, avgMv, pct);
  return pct;
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
