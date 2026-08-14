// Host-side check of the pure helpers. Build and run: ./tests/run.sh
#include <cstdio>
#include <cstdlib>
#include "../sensor/sensor_math.h"

static int failures = 0;

static void check(bool ok, const char *what) {
  if (!ok) { printf("FAIL %s\n", what); failures++; }
  else     { printf("ok   %s\n", what); }
}

static void testBackoff() {
  uint32_t prev = 0;
  bool monotonic = true, capped = true, positive = true;
  for (uint8_t step = 0; step <= 20; step++) {
    uint32_t ms = backoffDelayMs(step);
    if (ms < prev) monotonic = false;
    if (ms > (uint32_t)TX_INTERVAL) capped = false;
    if (ms == 0) positive = false;
    prev = ms;
  }
  check(monotonic, "backoff is monotonic over steps 0..20");
  check(capped, "backoff never exceeds TX_INTERVAL");
  check(positive, "backoff is never zero");
  check(backoffDelayMs(0) == 30000UL, "first backoff is 30 s");
  check(backoffDelayMs(1) == 60000UL, "second backoff is 60 s");
  check(backoffDelayMs(255) == (uint32_t)TX_INTERVAL, "saturated step hits the cap");
  check(BACKOFF_MAX_MS == TX_INTERVAL, "cap equals the uplink period");
  // 30000 << MAX_BACKOFF_STEP must stay inside uint32_t.
  check((uint64_t)BACKOFF_BASE_MS << MAX_BACKOFF_STEP <= 0xFFFFFFFFull, "shift cannot overflow");
}

static void testOcv() {
  check(ocvToPercent(2799) < 0, "2799 mV is out of range");
  check(ocvToPercent(4401) < 0, "4401 mV is out of range");
  check(ocvToPercent(2800) == 0, "2800 mV clamps to 0 %");
  check(ocvToPercent(3100) == 0, "3100 mV is 0 %");
  check(ocvToPercent(4190) == 100, "4190 mV is 100 %");
  check(ocvToPercent(4400) == 100, "4400 mV clamps to 100 %");
  check(ocvToPercent(3800) == 60, "3800 mV is 60 % (table entry 8)");
  check(ocvToPercent(3530) == 30, "3530 mV is 30 %");

  int prev = -1;
  for (uint32_t mv = 2800; mv <= 4400; mv++) {
    int pct = ocvToPercent(mv);
    if (pct < 0 || pct > 100) { printf("FAIL %u mV -> %d %%\n", mv, pct); failures++; return; }
    if (pct < prev) { printf("FAIL non-monotonic at %u mV: %d after %d\n", mv, pct, prev); failures++; return; }
    prev = pct;
  }
  check(true, "percentage is monotonic and bounded over 2800..4400 mV");
}

int main() {
  testBackoff();
  testOcv();
  if (failures) printf("\n%d FAILURES\n", failures);
  else          printf("\nall passed\n");
  return failures ? 1 : 0;
}
