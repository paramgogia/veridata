# Veridata hardware: current state (as of this chat)

## Boards
- Main board: NodeMCU ESP8266 (ESP-12E), Windows laptop, Arduino IDE 2.x, port COM8
  - Board setting: NodeMCU 1.0 (ESP-12E Module), esp8266 core 3.1.2, Serial Monitor 115200
  - This is NOT an ESP32 DevKit. The older plan (firmware/veridata_main with mbedtls P-256 /sign, /pubkey) assumed an ESP32; it needs adapting for ESP8266 (lighter ECDSA library, or sign on the backend in dev mode).
- Camera: ESP32-CAM (AI-Thinker). Flashed once with the stock CameraWebServer example (esp32 core 2.0.17), using the NodeMCU as a USB-serial adapter (NodeMCU RST->GND, RX->U0R, TX->U0T, CAM IO0->GND during upload; all removed afterwards). It runs standalone over WiFi (2.4 GHz). Endpoints: http://<cam-ip>/capture and http://<cam-ip>:81/stream. The CAM IP was not recorded in this chat.
- No servo, no keypad, no ultrasonic (yet), no resistors, no capacitors available.

## Power
- NodeMCU powered over micro-USB from the laptop.
- CAM 5V <- NodeMCU VIN, CAM GND <- GND (these may be unplugged during troubleshooting; CAM current spikes may disturb the NodeMCU 3.3 V).
- 3.3 V for sensors is taken from the NodeMCU 3V3 pin, possibly via a breadboard strip (unverified; strips can be split in the middle).
- All grounds common.

## Current wiring (NodeMCU pins)
| Part | Part pin | NodeMCU pin |
| IR obstacle module | VCC | 3V3 |
| IR obstacle module | GND | GND |
| IR obstacle module | OUT | D2 (GPIO4), active-LOW = object |
| RC522 RFID | 3.3V | 3V3 (3.3 V only) |
| RC522 RFID | GND | GND |
| RC522 RFID | RST | 3V3 (tied high, RST not used by firmware) |
| RC522 RFID | SDA/SS | D8 (GPIO15) |
| RC522 RFID | SCK | D5 (GPIO14) |
| RC522 RFID | MOSI | D7 (GPIO13) |
| RC522 RFID | MISO | D6 (GPIO12) |
| RC522 RFID | IRQ | not connected |
| DHT (3-pin module, type unknown: DHT22 or DHT11) | + | 3V3 |
| DHT (3-pin module) | DATA/OUT/S | D4 (GPIO2) |
| DHT (3-pin module) | - | GND |
| On-board LED | - | GPIO16 (D0), active-LOW, used by the sketch (not LED_BUILTIN, to keep it off D4) |
| ESP32-CAM | 5V / GND | NodeMCU VIN / GND (power only, no data wires) |

Not wired yet: buzzer (planned D1, 3-pin active module, may be active-LOW), ultrasonic HC-SR04.
If the ultrasonic is added later (needs a 1k+2k divider on ECHO): TRIG D1, ECHO D2, IR OUT moves to A0, buzzer to D0.

## Status of each part
- IR (D2): WORKING. Serial shows "IR: OBJECT detected" / "IR: clear" as a hand moves. Flickers near its range edge (adjust the module's potentiometer).
- RC522: INTERMITTENT. Reports version 0x12 (a clone chip version, works with the MFRC522 library) at times, then flips to 0x00 (not found). Earlier it was 0x00 consistently. No tag has been read yet. Suspects: loose or unsoldered header pins, bad jumper or breadboard contact, 3.3 V sag (CAM on the same supply), split breadboard strip.
- DHT: NOT WORKING. "no valid reading" with auto-detect of both DHT22 and DHT11. Pin order or labels on the 3-pin module are unverified (some modules are S/+/-, with + in the middle). The startup "DHT data line idle level" line was not yet captured.
- ESP32-CAM: flashed and test run reported done; stream while sensors run not yet confirmed.

## Software currently on the NodeMCU
Arduino sketch (test only), libraries: MFRC522 (GithubCommunity), DHT sensor library (Adafruit) + Adafruit Unified Sensor.
- Prints a self-check at boot (IR state, DHT idle level, RC522 version), then a status line every 2 s: IR | DHT reading | RFID status | tags read | last tag, plus event lines for IR changes and RFID tags.
- RC522 is re-checked every 5 s and re-initialized if missing.

## Known gotchas
- Uploading to the NodeMCU sometimes times out while D4 or D8 are wired (boot-strapping pins). Unplug the D4 and D8 wires, upload, then replug. Hold FLASH while tapping RST if still failing.
- Serial Monitor shows garbage at the start (74880 baud boot message); this is normal.
- ESP8266 pins are not 5 V tolerant; RC522, IR and DHT must stay on 3.3 V.

## Still to build (from the Veridata spec)
- NodeMCU WiFi firmware exposing sensors (IR, DHT, RFID UID, later ultrasonic) as JSON, e.g. GET /sensors, plus a dev-mode capture-manifest signing path.
- Backend env: CAM_CAPTURE_URL=http://<cam-ip>/capture, CAM_STREAM_URL=http://<cam-ip>:81/stream, DEVICE_CONTROL_URL=http://<nodemcu-ip>
- Dashboard shows live stream, sensor readings, RFID association; RFID is optional metadata, not proof of authenticity.