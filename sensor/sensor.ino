#include <SPI.h>
#include <RadioLib.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include "HT_SSD1306Wire.h"
#include <EEPROM.h>
#include "../settings.h"

/* =========================================================
   Display (Heltec native driver)
   ========================================================= */

static SSD1306Wire display(
  0x3c,
  500000,
  SDA_OLED,
  SCL_OLED,
  GEOMETRY_128_64,
  RST_OLED
);

SX1262 radio = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY);
Adafruit_BME280 bme;

/* =========================================================
   Globals
   ========================================================= */

uint8_t sensorID = 1;
uint32_t msgCounter = 0;

bool gatewayFound = false;
bool waitingAck = false;

unsigned long lastTx = 0;
bool firstTx = true;

bool screenOn = false;
unsigned long screenTimer = 0;

volatile bool receivedFlag = false;
int retryCount = 0;

bool bmeFound = false;
bool batteryAvailable = true;   // battery ADC always readable, but we keep flag

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
  display.clear();
  display.setTextAlignment(TEXT_ALIGN_LEFT);
  display.setFont(ArialMT_Plain_16);
  display.drawString(0, 16, l1);
  display.drawString(0, 36, l2);
  display.display();

  screenOn = true;
  screenTimer = millis();
}

/* =========================================================
   Battery
   ========================================================= */

float readBatteryVoltage() {
  int raw = analogRead(BATTERY_PIN);
  float voltage = (raw / ADC_RES) * ADC_REF;
  return voltage * VOLTAGE_DIVIDER_RATIO;
}

/* =========================================================
   EEPROM
   ========================================================= */

void loadSensorID() {
  EEPROM.begin(EEPROM_SIZE);
  sensorID = EEPROM.read(SENSOR_ID_ADDR);

  if (sensorID == 0xFF || sensorID == 0)
    sensorID = 1;
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

  radio.setDio1Action(setFlag);

  Serial.println("Radio ready");
  return true;
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
}

void sendPing() {
  String msg = "PING|" + String(sensorID);
  transmit(msg);
}

void sendSensorData() {
  String temperature = "nil";
  String humidity = "nil";
  String pressure = "nil";
  String battery = "nil";

  if (bmeFound) {
    temperature = String(bme.readTemperature(), 2);
    humidity = String(bme.readHumidity(), 2);
    pressure = String(bme.readPressure() / 100.0F, 2);
  }

  if (batteryAvailable) {
    battery = String(readBatteryVoltage(), 2);
  }

  String msg =
    "DATA|" +
    String(sensorID) + "|" +
    temperature + "|" +
    humidity + "|" +
    pressure + "|" +
    battery + "|" +
    String(msgCounter);

  waitingAck = true;
  retryCount = 0;

  transmit(msg);
}

/* =========================================================
   RX
   ========================================================= */

void processPacket(String msg) {
  Serial.println("RX: " + msg);

  if (msg.startsWith("PONG")) {
    gatewayFound = true;
    showMessage("Gateway", "Connected");
    return;
  }

  if (msg.startsWith("ACK")) {
    waitingAck = false;
    retryCount = 0;
    msgCounter++;
    showMessage("ACK", "OK");
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
    processPacket(msg);
  }

  radio.startReceive();
}

/* =========================================================
   Button
   ========================================================= */

void handleButton() {
  static bool lastState = HIGH;

  bool current = digitalRead(BUTTON_PIN);

  if (lastState == HIGH && current == LOW) {
    sensorID++;

    if (sensorID > MAX_SENSORS)
      sensorID = 1;

    saveSensorID();

    showMessage("New Sensor ID", String(sensorID));
    delay(300);
  }

  lastState = current;
}

/* =========================================================
   Setup
   ========================================================= */

void setup() {
  Serial.begin(115200);
  delay(1000);

  VextON();
  delay(100);

  display.init();
  display.setFont(ArialMT_Plain_10);

  showMessage("Sensor Boot", "V3");

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  pinMode(BATTERY_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(BATTERY_PIN, ADC_11db);

  loadSensorID();

  bmeFound = bme.begin(0x76);

  if (bmeFound) {
    Serial.println("BME280 OK");
    showMessage("BME280", "Detected");
  } else {
    Serial.println("BME280 not found");
    showMessage("BME280", "Missing");
  }

  display.clear();
  display.drawString(0, 0, "Sensor Boot V3");
  display.drawString(0, 16, bmeFound ? "BME: OK" : "BME: MISSING");
  display.display();
  delay(1500);

  initRadio();
  radio.startReceive();

  lastTx = millis();
}

/* =========================================================
   Loop
   ========================================================= */

void loop() {
  handleReceive();
  handleButton();

  if (screenOn && millis() - screenTimer > SCREEN_TIMEOUT) {
    display.clear();
    display.display();
    screenOn = false;
  }

  if (!gatewayFound) {
    if (millis() - lastTx > 2000) {
      sendPing();
      lastTx = millis();
    }
    return;
  }

  if (!waitingAck &&
      (millis() - lastTx >= TX_INTERVAL || firstTx)) {

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
}
