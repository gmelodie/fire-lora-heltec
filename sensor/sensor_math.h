#pragma once

#include <stdint.h>
#include "settings.h"

// Gateway-lost backoff: 30s, 60s, 120s ... capped at one uplink period.
inline uint32_t backoffDelayMs(uint8_t step) {
  uint8_t s = (step > MAX_BACKOFF_STEP) ? (uint8_t)MAX_BACKOFF_STEP : step;
  uint32_t ms = (uint32_t)BACKOFF_BASE_MS << s;
  return (ms > (uint32_t)BACKOFF_MAX_MS) ? (uint32_t)BACKOFF_MAX_MS : ms;
}

// 1S LiPo open-circuit curve, 5 % per entry from 100 % down to 0 %.
inline int ocvToPercent(uint32_t batMv) {
  static const uint16_t OCV[] = {
    4190, 4120, 4050, 4020, 3990, 3940, 3890, 3845, 3800, 3760,
    3720, 3675, 3630, 3580, 3530, 3475, 3420, 3360, 3300, 3200, 3100
  };
  const int NUM_OCV = 21;

  // Outside a real cell's range the reading is an ADC glitch, not a discharged battery.
  if (batMv < 2800 || batMv > 4400) return -1;

  if (batMv >= OCV[0]) return 100;
  if (batMv <= OCV[NUM_OCV - 1]) return 0;

  const int PCT_STEP = 100 / (NUM_OCV - 1);
  for (int j = 0; j < NUM_OCV - 1; j++) {
    if (batMv >= OCV[j + 1]) {
      return (NUM_OCV - j - 2) * PCT_STEP
           + (int)((batMv - OCV[j + 1]) * PCT_STEP / (OCV[j] - OCV[j + 1]));
    }
  }
  return 0;
}
