#include <SPI.h>
#include <Wire.h>
#include <RH_RF95.h>
#include <U8g2lib.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "secrets.h"

/* -----------------------
   Safe mode config
   ----------------------- */

#define WIFI_CONNECT_TIMEOUT 15000
#define WIFI_RETRY_INTERVAL  30000

bool wifiConnected = false;
unsigned long lastWifiRetry = 0;

/* -----------------------
   LoRa pin configuration
   ----------------------- */

#define RFM95_CS   18
#define RFM95_RST  14
#define RFM95_INT  26
#define RF95_FREQ  915.0

/* -----------------------
   Display pin configuration
   ----------------------- */

#define D_SCL 15
#define D_SDA 4
#define D_RST 16

/* -----------------------
   Objects
   ----------------------- */

U8G2_SSD1306_128X64_NONAME_F_SW_I2C display(
    U8G2_R0,
    D_SCL,
    D_SDA,
    D_RST
);

RH_RF95 rf95(RFM95_CS, RFM95_INT);

/* -----------------------
   Helpers
   ----------------------- */

void loraReset()
{
    pinMode(RFM95_RST, OUTPUT);
    digitalWrite(RFM95_RST, LOW);
    delay(20);
    digitalWrite(RFM95_RST, HIGH);
    delay(20);
}

void drawCentered(const char *text, int y)
{
    int16_t w = display.getStrWidth(text);
    int x = (128 - w) / 2;
    display.drawStr(x, y, text);
}

/* -----------------------
   WiFi Helpers
   ----------------------- */

bool connectWiFi()
{
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    Serial.print("Connecting WiFi");

    int retries = 0;

    while (WiFi.status() != WL_CONNECTED && retries < 20)
    {
        delay(500);
        Serial.print(".");
        retries++;
    }

    wifiConnected = WiFi.status() == WL_CONNECTED;

    if (wifiConnected)
    {
        Serial.println("\nWiFi OK");
        return false;
    }

    Serial.println("\nWiFi FAILED");
    return true;
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
        connectWiFi();
    }
}

/* -----------------------
   HTTPS Post (environment sensors)
   ----------------------- */

void postToApi(uint8_t sensorID, String temp, String hum, String pres, uint32_t counter, int16_t rssi)
{
    if (!wifiConnected)
        return;

    WiFiClientSecure client;
    client.setCACert(API_CERT);

    HTTPClient https;

    if (!https.begin(client, API_URL))
    {
        Serial.println("HTTPS begin failed");
        return;
    }

    https.addHeader("Content-Type", "application/json");
    https.addHeader("X-API-Password", API_PASSWORD);

    String json =
    "{"
    "\"sensor_id\":" + String(sensorID) + ","
    "\"temperature\":" + temp + ","
    "\"humidity\":" + hum + ","
    "\"pressure\":" + pres + ","
    "\"counter\":" + String(counter) + ","
    "\"rssi\":" + String(rssi) +
    "}";

    int code = https.POST(json);

    Serial.print("HTTPS Response: ");
    Serial.println(code);

    https.end();
}

/* -----------------------
   HTTPS Post (battery)
   ----------------------- */

void postBattery(uint8_t sensorID, String voltage, uint32_t counter, int16_t rssi)
{
    if (!wifiConnected)
        return;

    WiFiClientSecure client;
    client.setCACert(API_CERT);

    HTTPClient https;

    String url = String(API_URL) + "/battery";

    if (!https.begin(client, url))
    {
        Serial.println("Battery HTTPS begin failed");
        return;
    }

    https.addHeader("Content-Type", "application/json");
    https.addHeader("X-API-Password", API_PASSWORD);

    String json =
    "{"
    "\"sensor_id\":" + String(sensorID) + ","
    "\"voltage\":" + voltage + ","
    "\"counter\":" + String(counter) + ","
    "\"rssi\":" + String(rssi) +
    "}";

    int code = https.POST(json);

    Serial.print("Battery HTTPS Response: ");
    Serial.println(code);

    https.end();
}

/* -----------------------
   Setup
   ----------------------- */

void setup()
{
    Serial.begin(115200);
    delay(500);

    display.begin();
    display.setFont(u8g2_font_ncenB08_tr);

    display.clearBuffer();
    drawCentered("Booting...", 20);
    display.sendBuffer();

    if(connectWiFi()) {
      configTime(0, 0, "pool.ntp.org");
      while (time(nullptr) < 100000)
      {
          delay(200);
      }
    }

    loraReset();

    if (!rf95.init())
    {
        Serial.println("LoRa init failed");

        display.clearBuffer();
        drawCentered("LoRa FAIL", 30);
        display.sendBuffer();

        while (1);
    }

    rf95.setFrequency(RF95_FREQ);
    rf95.setTxPower(23, false);

    Serial.println("LoRa Gateway Ready");

    display.clearBuffer();
    drawCentered("LoRa RX Ready", 20);
    display.sendBuffer();
}

/* -----------------------
   Loop
   ----------------------- */

void loop()
{
    maintainWiFi();

    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf);

    if (!rf95.available())
    {
        delay(50);
        return;
    }

    if (!rf95.recv(buf, &len))
        return;

    buf[len] = '\0';

    String message = String((char*)buf);
    int16_t rssi = rf95.lastRssi();

    Serial.println("Received: " + message);
    Serial.print("RSSI: ");
    Serial.println(rssi);

    /* ---- Handle PING ---- */

    if (message.startsWith("PING|"))
    {
        uint8_t id = message.substring(5).toInt();

        String pong = "PONG|" + String(id);

        rf95.send((uint8_t*)pong.c_str(), pong.length());
        rf95.waitPacketSent();

        return;
    }

    /* ---- Handle Battery Packet ---- */

    if (message.startsWith("BAT|"))
    {
        int p1 = message.indexOf('|');
        int p2 = message.indexOf('|', p1 + 1);
        int p3 = message.indexOf('|', p2 + 1);

        if (p1 == -1 || p2 == -1 || p3 == -1)
            return;

        uint8_t sensorID = message.substring(p1 + 1, p2).toInt();
        String voltage = message.substring(p2 + 1, p3);
        uint32_t counter = message.substring(p3 + 1).toInt();

        String ack = "ACK|" + String(sensorID) + "|" + String(counter);
        rf95.send((uint8_t*)ack.c_str(), ack.length());
        rf95.waitPacketSent();

        postBattery(sensorID, voltage, counter, rssi);

        display.clearBuffer();
        display.setCursor(0, 20);
        display.print("Battery Node");
        display.setCursor(0, 36);
        display.print("ID:");
        display.print(sensorID);
        display.setCursor(0, 52);
        display.print("V:");
        display.print(voltage);
        display.print(" RSSI:");
        display.print(rssi);
        display.sendBuffer();

        return;
    }

    /* ---- Parse Environment Sensor Packet ---- */

    int p1 = message.indexOf('|');
    int p2 = message.indexOf('|', p1 + 1);
    int p3 = message.indexOf('|', p2 + 1);
    int p4 = message.indexOf('|', p3 + 1);

    if (p1 == -1 || p2 == -1 || p3 == -1 || p4 == -1)
        return;

    uint8_t sensorID = message.substring(0, p1).toInt();
    String temp = message.substring(p1 + 1, p2);
    String hum  = message.substring(p2 + 1, p3);
    String pres = message.substring(p3 + 1, p4);
    uint32_t counter = message.substring(p4 + 1).toInt();

    String ack = "ACK|" + String(sensorID) + "|" + String(counter);
    rf95.send((uint8_t*)ack.c_str(), ack.length());
    rf95.waitPacketSent();

    postToApi(sensorID, temp, hum, pres, counter, rssi);

    display.clearBuffer();

    display.setCursor(0, 12);
    display.print("Sensor: ");
    display.print(sensorID);

    display.setCursor(0, 24);
    display.print("Temp: ");
    display.print(temp);

    display.setCursor(0, 36);
    display.print("Hum: ");
    display.print(hum);

    display.setCursor(0, 48);
    display.print("Press: ");
    display.print(pres);

    display.setCursor(0, 60);
    display.print("RSSI:");
    display.print(rssi);

    display.sendBuffer();
}
