# Hardware setup

One logical device = **ESP32-CAM** (camera) + **ESP32 DevKit** (sensors, servo, RFID, signing key). Both join the same 2.4 GHz Wi-Fi as the laptop running the backend.

## ESP32-CAM
Flash the stock Arduino example **ESP32 → Camera → CameraWebServer** (board: AI Thinker ESP32-CAM). It exposes two endpoints:
- `http://<cam-ip>/capture` (JPEG)
- `http://<cam-ip>:81/stream` (MJPEG)

Set them as `CAM_CAPTURE_URL` / `CAM_STREAM_URL`, or enter them when registering the device. The backend proxies the stream, so the camera only ever has one client.

## ESP32 main board — `firmware/veridata_main`
Use Arduino IDE with board **ESP32 Dev Module** and core 2.0.x, plus the **MFRC522** library (miguelbalboa). Set `WIFI_SSID` and `WIFI_PASSWORD`, then flash. The serial monitor prints the board's IP and the device public key.

| Part | Pin | ESP32 |
|---|---|---|
| HC-SR04 | VCC / GND | 5V (VIN) / GND |
| | TRIG | GPIO 26 |
| | ECHO | GPIO 25 **through a 1 kΩ / 2 kΩ divider** (5V → 3.3V) |
| IR obstacle module | VCC / GND / OUT | 3V3 / GND / GPIO 27 (active-low; flip `IR_ACTIVE_LOW` if needed) |
| SG90 servo | signal | GPIO 13 (power from 5V, common GND) |
| RC522 RFID | SDA(SS) / SCK / MOSI / MISO / RST | GPIO 5 / 18 / 23 / 19 / 22 — **3.3V only** |
| ESP32-CAM | 5V / GND | solid 5V ≥ 1 A supply, common GND |

Mount the ESP32-CAM on the servo horn so the servo pans the capture angle.

## What each sensor contributes
- **Camera**: the media itself; its sha256 is signed.
- **Ultrasonic**: distance-to-subject in every manifest (e.g. shelf depth for stock-out detection, framing distance for leaf close-ups).
- **IR**: a digital presence/obstacle flag. We don't claim thermal imaging from this module.
- **Servo**: the capture angle, recorded in the manifest and controllable from the dashboard.
- **RFID**: the tag UID in the field at capture time is attached to the manifest and can be associated with a SKU, pallet or location. It is optional metadata and does not prove an object's authenticity or ownership.

## Signing modes
- `device-hardware`: at registration the backend calls `GET /pubkey` on the board. At capture it calls `GET /sign?digest=<sha256 of canonical manifest>`. The private key never leaves the board.
- `dev-software`: the fallback when the board isn't reachable at registration. The platform generates and wraps the key, and every manifest and Proof Card labels it as dev-software.

## Status
The firmware is written for ESP32 core 2.0.x, but it has **not yet been compiled or validated on the physical rig**. If the board is offline, the dashboard shows it as offline. Use a *simulated* device for software demos.
