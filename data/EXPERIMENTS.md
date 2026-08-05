# Experiment and dataset inventory

Single source of truth for the field campaigns. Regenerate the labelled data with
`python3 scripts/build_dataset.py`.

| File | Content |
|---|---|
| `readings_raw.json` | Full dump of the API, 806 rows, row ids 1 to 806 with no gaps |
| `readings_labelled.csv` | Every reading tagged with experiment, node, position, distance and per-field validity |
| `inmet_a711_2026.csv` | INMET A711 hourly reference, Jan to Jul 2026, from `portal.inmet.gov.br/uploads/dadoshistoricos/2026.zip` |

Timestamps in the raw dump are UTC epoch seconds, written by the API when the gateway
posts. Local time is UTC−3 with no daylight saving.

## Reference points

- Gateway: −21.979322, −47.883435. Fixed for every experiment.
- INMET station A711 (SAO CARLOS): −21.98028, −47.88389, altitude 859 m, **120 m from the
  gateway**. It records precipitation, pressure, global radiation, air temperature, dew
  point, relative humidity, wind speed, wind direction and gust, hourly.

## Physical nodes

The `sensor_id` in a packet is one byte read from EEPROM address 0. When a board is
flashed without the `sensor_id` argument to `recompile.sh`, that byte keeps whatever value
it held, so **the id is not a stable identity**. Boards below are keyed by hardware.

| Node | Ids reported | Experiments | Sensor state | Fate |
|---|---|---|---|---|
| N1 | 1 | F1, I1 | BME280 answers on I2C but returns invalid temperature and pressure | Retired after I1 |
| N2 | 15, 2 | F1, I1 | Humidity pinned at exactly 100 %, then total BME loss | Water damage |
| N3 | 1, 3, 6 | X, I2, F2 | All fields valid throughout | Water damage, died 24 May |
| N4 | 67, 70 | F3 | BME280 never detected, no environmental data | Ran to battery exhaustion |
| N5 | 222, 224 | F3 | All fields valid | Battery exhausted after 28 h |

Alias evidence. In F1, id 2 appears for 2 packets after id 15 stops and carries the same
pinned humidity. In F3, id 70 carries N4's missing-BME signature and a battery level on
N4's discharge curve; id 224 carries N5's valid BME data and a battery level on N5's
curve. Ids 222 and 67 overlap for 28.3 h with packets 3 s apart, so they are two boards,
not one.

## Positions

| Position | Coordinates | Distance to gateway | Used by |
|---|---|---|---|
| A | −21.9792439, −47.8843463 | 94.4 m | F1 N2 |
| B | −21.9793505, −47.8841408 | 72.8 m | F1 N1 |
| C | −21.9783096, −47.8844080 | 150.8 m | F2 N3 |
| D | −21.9790620, −47.8840620 | 70.8 m | F3 N4 |
| E | −21.9793889, −47.8841667 | 75.8 m | F3 N5 |
| home | not applicable | 4 m (I1, one wall), 2 m (I2, no walls) | I1, I2 |

All field nodes were mounted 2 m above ground. The paper's current figure of 85 m matches
no measured position and needs replacing.

## Experiments

| Exp | Window (UTC) | Duration | SF | TX | Interval | Enclosure | Site | Nodes | Status |
|---|---|---|---|---|---|---|---|---|---|
| F1 | 28 Apr 15:34 – 30 Apr 17:03 | 47.9 h | 7 | 14 dBm | 90 min | sealed | field | N1 at B, N2 at A | keep, radio and battery only |
| I1 | 1 May 02:10 – 3 May 09:40 | 54.0 h | 7 | 14 dBm | 90 min | sealed | indoor | N1, N2 | keep as near-field control for F1 |
| X | 9 May | — | 7 then 10 | 14 then 16 dBm | 90 min | sealed | indoor | N3 | **dropped**, straddles a config change |
| I2 | 15 May 01:16 – 15 May 16:16 | 15.0 h | 10 | 16 dBm | 90 min | sealed | indoor | N3 | keep as near-field control for F2 |
| F2 | 19 May 12:46 – 24 May 02:53 | 109.1 h | 10 | 16 dBm | 60 min | sealed | field | N3 at C | keep, full environmental run |
| F3 | 8 Jul 19:19 – 18 Jul 01:44 | 221.4 h | 11 | 16 dBm | 60 min | vented | field | N4 at D, N5 at E | keep |

F3 has two phases. Both nodes ran from 8 Jul 19:19 to 9 Jul 23:37 (28.3 h). N5 then reached
0 % battery, and N4 continued alone for a further 192.1 h. Report F3 as a single-node
experiment on N4, and use N5 only for its dry-season environmental sample.

A deployment on 3 July produced no stored data at all. See "Lost campaign" below.

## Per-run results

| Exp / node | Packets | PDR | Lost | RSSI mean / min | Battery | Valid T / RH / p |
|---|---|---|---|---|---|---|
| F1 / N1 | 33 | 100 % | 0 | −61.4 / −69 | 91→0 % | 0 / 33 / 0 |
| F1 / N2 | 33 | 100 % | 0 | −104.6 / −114 | 98→45 % | 33 / 0 / 33 |
| I1 / N1 | 37 | 100 % | 0 | −21.4 / −25 | 57→52 % | 0 / 37 / 0 |
| I1 / N2 | 37 | 100 % | 0 | −27.5 / −32 | 34→0 % | 37 / 0 / 37 |
| I2 / N3 | 10 | 100 % | 0 | −14.5 / −32 | 93→89 % | 10 / 10 / 10 |
| F2 / N3 | 113 | 100 % | 0 | −112.5 / −127 | 74→68 % | 113 / 113 / 113 |
| F3 / N4 | 223 | 99.6 % | 1 | −106.9 / −120 | 69→2 % | 0 / 0 / 0 |
| F3 / N5 | 36 | 100 % | 0 | −89.2 / −94 | 15→4 % | 36 / 36 / 36 |

Delivery is measured from packet counters and is post-retry; the firmware retries a frame
up to 3 times. Every battery is a 500 mAh LiPo.

## Failure reasons

**N1, invalid temperature and pressure.** Temperature reads exactly −143.99 °C and pressure
480 to 563 hPa from the first packet on 26 April, after 16 consecutive days without rain.
`bme.begin()` succeeded, so the chip answered on I2C, but the calibration read did not.
Humidity stayed in a plausible range, yet it is computed from the same corrupted
compensation state, so treat every N1 field as unusable. Cause: the connection to the
board, not water.

**N2, humidity pinned at 100 %.** Exactly 100.00 % on all 61 outdoor packets and 40 of 48
indoor packets, with temperature valid on 60 of 61 and pressure on 60 of 61. The value
persisted for three days indoors. The board later stopped answering on I2C. Cause: water
in the enclosure. Confirmed by the team.

**N3, sudden death at 24 May 02:53.** All 113 readings valid, then transmission stopped with
the battery still at 68 %, RSSI normal at −115 dBm and no reboot. Internal humidity had
risen monotonically every day: daily means 80.9, 92.0, 95.1, 94.6, 96.0, 97.3 %. The last
reading was 97.47 % at 16.95 °C, within 0.4 °C of saturation. 17.6 mm of rain fell during
the run, and 28 of 109 hours had a dew point depression at or below 1 °C. Cause: water in
the enclosure. Confirmed by the team.

**N4, no environmental data.** `bme.begin()` failed on every boot, so the firmware sent
`nil` for temperature, humidity and pressure. It began on the first packet, 12 days after
the last measurable rain. Cause: the sensor was not attached to the board.

**N5, battery exhaustion.** Started the deployment at 19 % and reached 0 % after 28.4 h. No
sensor fault.

## Power

Only F3 N4 crosses the full discharge curve, from 69 % to 2 % over 221.4 h. That gives
0.303 %/h, a full-charge lifetime of 330 h (13.8 days) and an average draw of **1.51 mA** on
a 500 mAh pack.

Do not compare %/h between runs. The reported percentage is a lookup from battery voltage
against a nonlinear LiPo curve. F2 moved only 74 % to 68 % because it sat on the flat
plateau for its whole run, so its 0.055 %/h says nothing about efficiency. N4 carried no
BME280, but a BME280 in forced mode at one sample per hour draws well under 10 µA, so the
effect on 1.51 mA is negligible.

## Enclosure bias

Dew point is the correct variable for comparing a node against A711, because solar heating
of the case raises temperature and lowers humidity but cannot change the dew point. Mean
dew point excess (node minus A711), by local hour:

| Local hour | N5, vented | N3, sealed |
|---|---|---|
| 00–07 | −4.0 to −5.3 °C | −0.5 to −0.9 °C |
| 09 | +13.9 °C | +0.2 °C |
| 13 | +6.5 °C | +2.4 °C |
| 14–16 | +7.4 to +8.9 °C | +1.1 to +3.2 °C |
| 18–23 | −2.1 to −5.3 °C | −0.1 to −0.6 °C |

Water condenses on the cold internal walls overnight and evaporates once the sun heats the
case. An excess of +13.9 °C cannot come from ambient air, so liquid water was present
inside. The vented case shows about five times the amplitude of the sealed one, which runs
counter to the expectation that a vent equilibrates the interior with ambient. Season
(July swings 12.2 °C daily against May's 7.4 °C), sun exposure and siting are all
confounded with the vent, since only one node ran per configuration, so the design
question is open.

The condensation itself is not in doubt. As mixing ratio, N5 held 21.5 g/kg at 09:00
against 8.7 g/kg at A711 and 5.7 against 8.4 g/kg at night. A siting difference gives a
standing offset, not a sign reversal twice a day.

This matters for the Monte Alegre Formula, which samples relative humidity at 13:00 local.
That hour sits inside the contaminated window. At 14:00 local, N5 read 58.0 % against 34 %
at A711, a 24 pp wet bias. FMA accumulates 100/RH, so an uncorrected node under-reports
fire danger.

## Weather context

| Exp | Rain in window | Dry days before start |
|---|---|---|
| F1 | 10.0 mm over 3.85 d | 16 |
| I1 | 0.0 mm | 1 |
| F2 | 17.6 mm over 4.59 d | 0, 16.2 mm fell the day before |
| F3 | 2.8 mm over 9.27 d | 11 |

F2 is a wet-season-tail run and F3 is a dry-season run. Only F3 offers the consecutive dry
days that FMA needs, and only N5 carries environmental data in that window.

## Lost campaign, 3 July

A deployment on 3 July stored zero rows. Row ids stay contiguous across the whole gap from
24 May to 8 July, so nothing was deleted; the readings never arrived. The gateway has no
store-and-forward:

- `gateway/gateway.ino:257` sends the ACK before the reading leaves the gateway.
- `gateway/gateway.ino:107` makes `httpsPost()` return false at once when WiFi is down.
- `gateway/gateway.ino:364` uses that result only to print a screen message, then discards
  the payload. There is no queue, no retry and no flash buffer.

So the nodes transmitted on schedule, received ACKs, treated each frame as delivered and
returned to deep sleep while the gateway dropped every reading. No firmware commit exists
between 27 May and today, and the TLS certificate is valid to April 2027 and is not
verified anyway, so the fault was the backhaul rather than the build. The data is not
recoverable, because the nodes keep no local copy.

Consequence for reporting: the delivery ratios above measure the LoRa link to the gateway
while the gateway is up. End-to-end availability for the 3 July campaign was 0 %. The radio
was never the weak link.

## Data hazards

1. **Bench packets.** 284 of 806 rows fall outside any deployment run. They are setup and
   deploy-mode bursts, recognisable by a counter that stays at 0 and a strong RSSI. Filter
   on `in_run == 1`.
2. **Receiver compression.** RSSI values above about −25 dBm are near the front-end limit.
   The F2 setup burst contains 0 and −1 dBm, which is physically impossible. Use indoor
   runs as a qualitative reference, not as a calibrated path-loss anchor.
3. **Unstable ids.** Always key on `node`, never on `sensor_id`. Pass the id explicitly to
   `recompile.sh` on future deployments.
4. **Battery percentage.** Nonlinear; see "Power".
5. **Enclosure humidity.** See "Enclosure bias". Sealed-case humidity is enclosure air.

## Provenance of the position assignments

The A and B assignment rests on inference, not on a field record. The intended
discriminator was the camera battery, but **no row in the database carries a camera battery
value**: the `--camera` flag reached `recompile.sh` on 30 April, the last day of F1, so the
field never populated. N1 is placed at B and N2 at A because the distance ordering matches
the signal ordering (N1 at −61.4 dBm and 72.8 m, N2 at −104.6 dBm and 94.4 m). The team
accepted this reading. Note that a 43 dB gap across a 22 m difference still comes mostly
from vegetation, so the assignment cannot be checked from RSSI alone. State it as reported
rather than as measured if a reviewer presses on it.

Position C for F2 is confirmed. A second coordinate recorded against the same board,
21°58'44.3"S 47°53'02.1"W at 63.1 m from the gateway, refers to an earlier candidate
location that never carried a full deployment. C at 150.8 m also fits F2's −112.5 dBm mean,
since N4 measured −106.9 dBm at 70.8 m.
