/* =========================================================
   Hardware configuration (Heltec WiFi LoRa 32 V3)
   ========================================================= */

#define LORA_CS    8
#define LORA_DIO1  14
#define LORA_RST   12
#define LORA_BUSY  13

/* =========================================================
   LoRa parameters
   ========================================================= */

#define RX_FREQ_MHZ 915.0f
#define RX_BW_KHZ 125.0f
// SF11 trades airtime for ~2.5 dB more link budget vs SF10 → longer reach. Sensor and
// gateway share this header (symlinked), so both stay in sync. Bumping SF roughly doubles
// time-on-air (DATA ~1.1s), so ACK_TIMEOUT below is widened to fit the round trip.
#define RX_SF 11
#define RX_CR 5
#define TX_POWER_DBM 16

/* =========================================================
   WiFi state
   ========================================================= */

#define WIFI_RETRY_INTERVAL 30000

/* =========================================================
   Battery
   ========================================================= */

#define BATTERY_PIN 1
#define ADC_CTRL_PIN 37
#define CAMERA_BATTERY_PIN 2
#define ADC_REF 3.3
#define ADC_RES 4095.0
#define VOLTAGE_DIVIDER_RATIO 2.0
// V3:   390k/100k divider with ADC loading effect → effective ~49x (auto-normalized to same as 4.9)
// V3.2: different resistors → empirically ~5.03x (measured: 829mV pin → 4170mV actual)
#define BATTERY_RATIO   4.9f


/* =========================================================
   Button
   ========================================================= */

#define BUTTON_PIN 0

/* =========================================================
   EEPROM
   ========================================================= */

#define EEPROM_SIZE 32
#define SENSOR_ID_ADDR 0

/* =========================================================
   Timing
   ========================================================= */

#ifndef TX_INTERVAL
#define TX_INTERVAL 3600000UL // 1 hour default; override with --interval flag in recompile.sh
#endif
#define ACK_TIMEOUT 3000  // SF11 round trip (DATA up ~1.1s + ACK down ~0.5s) needs headroom
#define MAX_RETRIES 3
#define SCREEN_TIMEOUT 3000
#define MAX_SENSORS 254

#define PING_INTERVAL_MS    2000UL
#define GATEWAY_SEARCH_MS   10000UL  // give up and sleep if no pong within this window
#define BACKOFF_BASE_MS     30000UL  // first backoff sleep: 30s
#define BACKOFF_MAX_MS      300000UL // cap at 5 min
#define MAX_BACKOFF_STEP    8        // prevents bit-shift overflow (30000 << 8 still fits uint32_t)

#define DEPLOY_PING_INTERVAL_MS  8000UL  // ping rate in deploy mode

/* =========================================================
   Battery to ADC VALUES
   ========================================================= */

#define BAT_100   1330
#define BAT_80    1269
#define BAT_50    1187
#define BAT_25    1107
#define BAT_10    970
#define BAT_DEAD  900


/* =========================================================
   SAMPLES
   ========================================================= */

#define NUM_ADC_SAMPLES 10

/* =========================================================
   I2C
   ========================================================= */

#define BME_SDA 4
#define BME_SCL 3



