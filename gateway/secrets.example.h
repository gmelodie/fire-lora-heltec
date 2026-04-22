#pragma once

// ── Regular WPA2 (home / office router) ───────────────────────────────────
// Leave USE_EAP commented out and fill in WIFI_PASS.
#define WIFI_SSID "your_wifi"
#define WIFI_PASS "your_password"

// ── Eduroam / WPA2-Enterprise ──────────────────────────────────────────────
// Uncomment USE_EAP and fill in the three EAP fields.
// WIFI_PASS is ignored when USE_EAP is defined.
// #define USE_EAP
// #define EAP_IDENTITY "user@university.edu"
// #define EAP_USERNAME "user@university.edu"
// #define EAP_PASSWORD "your_eap_password"

// ── API ────────────────────────────────────────────────────────────────────
#define API_PASSWORD "your_password"
#define API_URL "https://192.168.68.68:8443"

/* Root certificate (PEM format) */
static const char *API_CERT PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIID......
.....YOUR CERT HERE.....
-----END CERTIFICATE-----
)EOF";
