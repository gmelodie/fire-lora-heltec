#include "LoRaWan_APP.h"
#include "Arduino.h"
#include "HT_SSD1306Wire.h"
#include <EEPROM.h>

#define RF_FREQUENCY             915000000UL   // 915 MHz
#define TX_OUTPUT_POWER          22            // dBm, max power
#define LORA_BANDWIDTH           1
#define LORA_SPREADING_FACTOR    11
#define LORA_CODINGRATE          1
#define LORA_PREAMBLE_LENGTH     8             // symbols
#define LORA_FIX_LENGTH_PAYLOAD_ON false       // dynamic payload
#define LORA_IQ_INVERSION_ON     false         // normal IQ

#if defined(WIFI_LORA_32_V3) || defined(WIFI_LORA_32_V2)
SSD1306Wire factory_display(0x3c, 500000, SDA_OLED, SCL_OLED, GEOMETRY_128_64, RST_OLED);
#endif

#define BATTERY_PIN         1
#define ADC_REF             3.3
#define ADC_RES             4095.0
#define VOLTAGE_DIVIDER_RATIO 2.0

#define EEPROM_SIZE         32
#define SENSOR_ID_ADDR      0

#define TX_INTERVAL         300000UL
#define ACK_TIMEOUT         2000
#define MAX_RETRIES         3

static RadioEvents_t RadioEvents;
bool lora_idle = true;

uint8_t sensorID = 1;
uint32_t msgCounter = 0;
unsigned long lastTx = 0;
bool firstTx = true;

char txpacket[64];

void loadSensorID() {
    EEPROM.begin(EEPROM_SIZE);
    sensorID = EEPROM.read(SENSOR_ID_ADDR);
    if(sensorID == 0xFF || sensorID == 0) sensorID = 1;
}

void saveSensorID() {
    EEPROM.write(SENSOR_ID_ADDR, sensorID);
    EEPROM.commit();
}

float readBatteryVoltage() {
    int raw = analogRead(BATTERY_PIN);
    float voltage = (raw / ADC_RES) * ADC_REF;
    voltage *= VOLTAGE_DIVIDER_RATIO;
    return voltage;
}

void showMessage(String l1, String l2="") {
#if defined(WIFI_LORA_32_V3) || defined(WIFI_LORA_32_V2)
    factory_display.clear();
    factory_display.drawString(0, 0, l1);
    if(l2.length() > 0) factory_display.drawString(0, 20, l2);
    factory_display.display();
#endif
}

void setup() {
    Serial.begin(115200);
    Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

#if defined(WIFI_LORA_32_V3) || defined(WIFI_LORA_32_V2)
    pinMode(Vext, OUTPUT);
    digitalWrite(Vext, LOW);
    delay(100);
    factory_display.init();
    factory_display.clear();
    factory_display.drawString(0,0,"Battery Node Booting");
    factory_display.display();
#endif

    pinMode(BATTERY_PIN, INPUT);
    loadSensorID();

    RadioEvents.TxDone = [](){ lora_idle = true; msgCounter++; Serial.println("TX done"); };
    RadioEvents.TxTimeout = [](){ lora_idle = true; Serial.println("TX Timeout"); };

    Radio.Init(&RadioEvents);
    Radio.SetChannel(RF_FREQUENCY);
    Radio.SetTxConfig(MODEM_LORA, TX_OUTPUT_POWER, 0, LORA_BANDWIDTH,
                       LORA_SPREADING_FACTOR, LORA_CODINGRATE,
                       LORA_PREAMBLE_LENGTH, LORA_FIX_LENGTH_PAYLOAD_ON,
                       true, 0, 0, LORA_IQ_INVERSION_ON, 3000);
}

void loop() {
    if(lora_idle && (millis() - lastTx >= TX_INTERVAL || firstTx)) {
        firstTx = false;
        lastTx = millis();

        float voltage = readBatteryVoltage();
        msgCounter++;

        // format: BAT|<sensorID>|<voltage>|<msgCounter>
        sprintf(txpacket, "BAT|%d|%.2f|%d", sensorID, voltage, msgCounter);

        Serial.printf("Sending: %s\n", txpacket);
        showMessage("Sending", txpacket);

        Radio.Send((uint8_t*)txpacket, strlen(txpacket));
        lora_idle = false;
    }

    Radio.IrqProcess();
}
