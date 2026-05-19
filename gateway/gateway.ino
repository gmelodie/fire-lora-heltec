#include <SPI.h>
#include <time.h>
#include <RadioLib.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <SSD1306Wire.h>
#include "secrets.h"
#include "settings.h"

/* =========================================================
   Display
   ========================================================= */

static SSD1306Wire display(0x3c, SDA_OLED, SCL_OLED);

void VextON()
{
  pinMode(Vext, OUTPUT);
  digitalWrite(Vext, LOW);
}

SX1262 radio = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY);

bool wifiConnected = false;
unsigned long lastWifiRetry = 0;
volatile bool receivedFlag = false;

/* =========================================================
   Display helpers
   ========================================================= */

void drawCentered(String text, int y)
{
  display.setTextAlignment(TEXT_ALIGN_CENTER);
  display.drawString(64, y, text);
}

void showBootScreen()
{
  display.clear();
  drawCentered("Gateway Boot", 20);
  drawCentered("Starting...", 36);
  display.display();
}

void showReady()
{
  display.clear();
  drawCentered("LoRa RX Ready", 28);
  display.display();
}

/* =========================================================
   WiFi
   ========================================================= */

bool connectWiFi()
{
  WiFi.disconnect(true);
  WiFi.mode(WIFI_STA);

#ifdef USE_EAP
  WiFi.begin(WIFI_SSID, WPA2_AUTH_PEAP, EAP_IDENTITY, EAP_USERNAME, EAP_PASSWORD);
#else
  WiFi.begin(WIFI_SSID, WIFI_PASS);
#endif

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20)
  {
    delay(500);
    Serial.print(".");
    retries++;
  }

  wifiConnected = WiFi.status() == WL_CONNECTED;

  return wifiConnected;
}

void maintainWiFi()
{
  if (WiFi.status() == WL_CONNECTED)
  {
    wifiConnected = true;
    return;
  }

  wifiConnected = false;

  if (millis() - lastWifiRetry > WIFI_RETRY_INTERVAL)
  {
    lastWifiRetry = millis();
    Serial.print("Maintaining WiFi");
    wifiConnected = connectWiFi();
    Serial.println(wifiConnected ? "\nWiFi OK" : "\nWiFi FAILED");
  }
}

/* =========================================================
   HTTPS
   ========================================================= */

bool httpsPost(String url, String payload)
{
  if (!wifiConnected)
    return false;

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient https;

  if (!https.begin(client, url))
  {
    Serial.println("HTTPS begin failed");
    return false;
  }

  https.addHeader("Content-Type", "application/json");
  https.addHeader("X-API-Password", API_PASSWORD);

  int code = https.POST(payload);

  Serial.print("HTTPS Response: ");
  Serial.println(code);

  https.end();
  return code > 0;
}

bool checkApi()
{
  if (!wifiConnected)
    return false;

  for (int attempt = 0; attempt < 3; attempt++)
  {
    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient https;
    if (!https.begin(client, API_URL "/readings/latest"))
    {
      delay(2000);
      continue;
    }

    https.addHeader("X-API-Password", API_PASSWORD);
    int code = https.GET();
    https.end();

    Serial.printf("API check attempt %d: %d\n", attempt + 1, code);

    if (code > 0)
      return true;

    showPacket("API ERR", String(code), "Retrying...");
    delay(2000);
  }

  return false;
}

/* =========================================================
   LoRa helpers
   ========================================================= */

void IRAM_ATTR setFlag(void)
{
  receivedFlag = true;
}

void sendAck(uint8_t id, uint32_t counter)
{
  String ack = "ACK|" + String(id) + "|" + String(counter);

  radio.standby();
  radio.transmit(ack);
  receivedFlag = false;
  radio.startReceive();
}

void sendPong(uint8_t id)
{
  String pong = "PONG|" + String(id);

  radio.standby();
  radio.transmit(pong);
  receivedFlag = false;
  radio.startReceive();
}

bool initRadio()
{
  int state = radio.begin(RX_FREQ_MHZ);

  if (state != RADIOLIB_ERR_NONE)
  {
    Serial.printf("LoRa init failed: code %d\n", state);
    return false;
  }

  radio.setSpreadingFactor(RX_SF);
  radio.setBandwidth(RX_BW_KHZ);
  radio.setCodingRate(RX_CR);
  radio.setOutputPower(TX_POWER_DBM);
  radio.setDio2AsRfSwitch();
  radio.setDio1Action(setFlag);
  radio.startReceive();

  return true;
}

/* =========================================================
   Packet handlers
   ========================================================= */

void showPacket(String title, String line2, String line3)
{
  display.clear();
  drawCentered(title, 12);
  drawCentered(line2, 32);
  drawCentered(line3, 50);
  display.display();
}

void handlePing(String msg)
{
  uint8_t id = msg.substring(5).toInt();
  sendPong(id);
  showPacket("PING", "Sensor " + String(id), "Responded");
}

String handleData(String msg, int16_t rssi)
{
  int p1 = msg.indexOf('|');
  int p2 = msg.indexOf('|', p1 + 1);
  int p3 = msg.indexOf('|', p2 + 1);
  int p4 = msg.indexOf('|', p3 + 1);
  int p5 = msg.indexOf('|', p4 + 1);
  int p6 = msg.indexOf('|', p5 + 1);
  int p7 = msg.indexOf('|', p6 + 1);
  if (p1 == -1 || p2 == -1 || p3 == -1 || p4 == -1 || p5 == -1 || p6 == -1 || p7 == -1)
    return "";

  uint8_t id = msg.substring(p1 + 1, p2).toInt();
  String temp = msg.substring(p2 + 1, p3);
  String hum = msg.substring(p3 + 1, p4);
  String pres = msg.substring(p4 + 1, p5);
  String batt = msg.substring(p5 + 1, p6);
  String camBatt = msg.substring(p6 + 1, p7);
  uint32_t counter = msg.substring(p7 + 1).toInt();

  sendAck(id, counter);

  showPacket(
      "Sensor " + String(id),
      "T " + temp + " H " + hum,
      "B " + batt + " RSSI " + String(rssi));
  auto jsonVal = [](const String &v) -> String { return v == "nil" ? "null" : v; };
  return "{\"sensor_id\":\"" + String(id) + "\","
         "\"temperature\":" + jsonVal(temp) + ","
         "\"humidity\":" + jsonVal(hum) + ","
         "\"pressure\":" + jsonVal(pres) + ","
         "\"battery\":" + jsonVal(batt) + ","
         "\"camera_battery\":" + jsonVal(camBatt) + ","
         "\"counter\":" + String(counter) + ","
         "\"rssi\":" + String(rssi) + "}";
}

/* =========================================================
   Setup
   ========================================================= */

void setup()
{
  Serial.begin(115200);
  delay(500);

  VextON();
  delay(100);

  pinMode(RST_OLED, OUTPUT);
  digitalWrite(RST_OLED, LOW);
  delay(20);
  digitalWrite(RST_OLED, HIGH);

  display.init();
  display.setFont(ArialMT_Plain_10);

  showBootScreen();

  wifiConnected = connectWiFi();
  Serial.println(wifiConnected ? "\nWiFi OK" : "\nWiFi FAILED");
  showPacket(wifiConnected ? "WiFi OK" : "WiFi FAILED", WiFi.localIP().toString(), "");
  delay(1000);

  if (wifiConnected)
  {
    configTime(0, 0, "pool.ntp.org");
    struct tm t;
    int tries = 0;
    while (!getLocalTime(&t) && tries++ < 6)
      delay(500);
    Serial.println(getLocalTime(&t) ? "NTP OK" : "NTP FAILED");
  }

  bool apiOk = checkApi();
  Serial.println(apiOk ? "API OK" : "API FAILED");
  showPacket(apiOk ? "API OK" : "API FAILED", API_URL, "");
  delay(1000);

  if (!initRadio())
  {
    showPacket("ERROR", "LoRa Failed", "");
    while (true)
      ;
  }
  Serial.println("Radio OK");

  showReady();
}

/* =========================================================
   Loop
   ========================================================= */

void loop()
{
  maintainWiFi();

  if (!receivedFlag)
    return;
  receivedFlag = false;

  String msg;
  int state = radio.readData(msg);

  if (state != RADIOLIB_ERR_NONE || msg.length() == 0)
  {
    radio.startReceive();
    return;
  }

  int16_t rssi = radio.getRSSI();

  Serial.println("Received: " + msg);
  Serial.print("RSSI: ");
  Serial.print(rssi);
  Serial.println(" dBm");

  if (msg.startsWith("PING|"))
  {
    handlePing(msg);  // sendPong() calls startReceive
    return;
  }

  if (msg.startsWith("DATA|")) {
    String payload = handleData(msg, rssi);  // sendAck() calls startReceive
    if (payload.length() > 0) {
      bool ok = httpsPost(API_URL "/sensor", payload);
      showPacket(ok ? "API OK" : "API FAILED", "", "");
    } else {
      radio.startReceive();  // parse failed, sendAck was not called
    }
    return;
  }

  radio.startReceive();  // unknown message type
  Serial.println();
}
