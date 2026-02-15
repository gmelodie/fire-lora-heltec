#include <SPI.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <RH_RF95.h>
#include <U8g2lib.h>
#include <EEPROM.h>

/* ================= LoRa ================= */
#define RFM95_CS   18
#define RFM95_RST  14
#define RFM95_INT  26
#define RF95_FREQ  915.0

RH_RF95 rf95(RFM95_CS, RFM95_INT);

/* ================= Display ================= */
#define D_SCL 15
#define D_SDA 4
#define D_RST 16

U8G2_SSD1306_128X64_NONAME_F_SW_I2C display(
    U8G2_R0,
    D_SCL,
    D_SDA,
    D_RST
);

/* ================= Sensor ================= */
Adafruit_BME280 bme;

/* ================= Button ================= */
#define BUTTON_PIN 0

/* ================= EEPROM ================= */
#define EEPROM_SIZE 32
#define SENSOR_ID_ADDR 0

/* ================= Timing ================= */
#define TX_INTERVAL 300000UL
#define ACK_TIMEOUT 2000
#define MAX_RETRIES 3
#define SCREEN_TIMEOUT 5000

#define MAX_SENSORS 25

/* ================= Globals ================= */
uint8_t sensorID = 1;
uint32_t msgCounter = 0;

unsigned long lastTx = 0;
bool firstTx = true;

bool screenOn = false;
unsigned long screenTimer = 0;

/* ====================================================== */
/* EEPROM */
/* ====================================================== */

void loadSensorID()
{
    sensorID = EEPROM.read(SENSOR_ID_ADDR);

    if (sensorID == 0xFF || sensorID == 0)
        sensorID = 1;
}

void saveSensorID()
{
    EEPROM.write(SENSOR_ID_ADDR, sensorID);
    EEPROM.commit();
}

/* ====================================================== */
/* Display */
/* ====================================================== */

void showMessage(String l1, String l2)
{
    display.clearBuffer();
    display.setFont(u8g2_font_ncenB08_tr);

    display.setCursor(0, 20);
    display.print(l1);

    display.setCursor(0, 40);
    display.print(l2);

    display.sendBuffer();

    screenOn = true;
    screenTimer = millis();
}

/* ====================================================== */
/* Ping receiver */
/* ====================================================== */

bool pingReceiver(int16_t &rssiOut)
{
    String ping = "PING|" + String(sensorID);

    rf95.send((uint8_t*)ping.c_str(), ping.length());
    rf95.waitPacketSent();

    unsigned long start = millis();

    while (millis() - start < 1500)
    {
        if (rf95.available())
        {
            uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
            uint8_t len = sizeof(buf);

            if (rf95.recv(buf, &len))
            {
                buf[len] = '\0';
                String resp = String((char*)buf);

                if (resp == ("PONG|" + String(sensorID)))
                {
                    rssiOut = rf95.lastRssi();
                    return true;
                }
            }
        }
    }

    return false;
}

/* ====================================================== */
/* Button */
/* ====================================================== */

void handleButton()
{
    static bool lastState = HIGH;

    bool current = digitalRead(BUTTON_PIN);

    if (lastState == HIGH && current == LOW)
    {
        sensorID++;
        if (sensorID > MAX_SENSORS)
            sensorID = 1;

        saveSensorID();

        Serial.print("New sensor ID: ");
        Serial.println(sensorID);

        showMessage("Testing ID:", String(sensorID));

        int16_t rssi = 0;
        bool ok = pingReceiver(rssi);

        if (ok)
            showMessage("Connection", "SUCCESS (RSSI: " + String(rssi) + ")");
        else
            showMessage("Connection", "FAILED");


        delay(200);
    }

    lastState = current;
}

/* ====================================================== */
/* ACK Send */
/* ====================================================== */

bool sendWithAck(String payload)
{
    for (int attempt = 1; attempt <= MAX_RETRIES; attempt++)
    {
        rf95.send((uint8_t*)payload.c_str(), payload.length());
        rf95.waitPacketSent();

        unsigned long start = millis();

        while (millis() - start < ACK_TIMEOUT)
        {
            if (rf95.available())
            {
                uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
                uint8_t len = sizeof(buf);

                if (rf95.recv(buf, &len))
                {
                    buf[len] = '\0';
                    String resp = String((char*)buf);

                    String expected =
                        "ACK|" + String(sensorID) + "|" + String(msgCounter);

                    if (resp == expected)
                        return true;
                }
            }
        }
    }

    return false;
}

/* ====================================================== */
/* Setup */
/* ====================================================== */

void setup()
{
    Serial.begin(115200);
    delay(500);

    pinMode(BUTTON_PIN, INPUT_PULLUP);

    EEPROM.begin(EEPROM_SIZE);
    loadSensorID();

    /* Display */
    display.begin();
    display.clearBuffer();
    display.sendBuffer();

    /* Sensor */
    if (!bme.begin(0x76))
    {
        Serial.println("BME280 not found!");
        while (1);
    }

    /* LoRa reset */
    pinMode(RFM95_RST, OUTPUT);
    digitalWrite(RFM95_RST, HIGH);
    delay(10);
    digitalWrite(RFM95_RST, LOW);
    delay(10);
    digitalWrite(RFM95_RST, HIGH);

    if (!rf95.init())
    {
        Serial.println("LoRa init failed!");
        while (1);
    }

    rf95.setFrequency(RF95_FREQ);
    rf95.setTxPower(23, false);

    Serial.print("Sensor ID: ");
    Serial.println(sensorID);
}

/* ====================================================== */
/* Loop */
/* ====================================================== */

void loop()
{
    handleButton();

    /* Screen auto off */
    if (screenOn && millis() - screenTimer > SCREEN_TIMEOUT)
    {
        display.clearBuffer();
        display.sendBuffer();
        screenOn = false;
    }

    /* Transmission */
    if (millis() - lastTx >= TX_INTERVAL || firstTx)
    {
        if (firstTx)
            firstTx = false;

        lastTx = millis();
        msgCounter++;

        float temperature = bme.readTemperature();
        float humidity = bme.readHumidity();
        float pressure = bme.readPressure() / 100.0F;

        String payload =
            String(sensorID) + "|" +
            String(temperature, 2) + "|" +
            String(humidity, 2) + "|" +
            String(pressure, 2) + "|" +
            String(msgCounter);

        Serial.println("Payload: " + payload);

        bool ok = sendWithAck(payload);

        if (!ok)
            Serial.println("Transmission failed after retries");
    }
}

