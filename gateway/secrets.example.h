#pragma once

#define WIFI_SSID "your_wifi"
#define WIFI_PASS "your_password"

#define API_PASSWORD "your_password"

/* Root certificate (PEM format) */
static const char *API_CERT PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIID......
.....YOUR CERT HERE.....
-----END CERTIFICATE-----
)EOF";

