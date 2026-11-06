# Veridata hardware: setup v2

Two independent boards that talk to the laptop over the same Wi-Fi hotspot. No data wires run between them.

```
 [Power bank] --USB--> [ESP32 DevKit]  (only a 5 V adapter; its own chip is held off)
                          VIN ----> 5V  [ESP32-CAM]  ~~Wi-Fi~~>  http://<cam-ip>/capture, :81/stream
                          GND ----> GND

 [Laptop] --USB--> [NodeMCU ESP8266] + IR + DHT + RC522  ~~Wi-Fi~~>  http://<sensor-ip>/sensors

 [Laptop] runs the Veridata backend, which polls both boards over Wi-Fi.
```

| Folder | Board | Arduino IDE board setting |
|---|---|---|
| `veridata_cam_v2/` | ESP32-CAM (AI-Thinker) | **AI Thinker ESP32-CAM** |
| `veridata_sensors_v2/` | NodeMCU ESP8266 | **NodeMCU 1.0 (ESP-12E Module)** |

Wi-Fi name and password are in `secrets.h` in each folder (gitignored, already filled in for hotspot `param`).
The old sketches in `../veridata_cam` and `../veridata_nodemcu` are unchanged.

---

## 1. Wiring

### 1A. ESP32-CAM + DevKit for FLASHING (one time only)

The DevKit acts as a USB-to-serial adapter. Its own ESP32 is held off by wiring **EN to GND**.

| From (DevKit) | To | Why |
|---|---|---|
| **EN** | DevKit **GND** | keeps the DevKit's own chip off |
| **VIN** (5V) | CAM **5V** | power (never use CAM 3V3) |
| **GND** | CAM **GND** | common ground |
| **TX** (TX0 / TXD0 / GPIO1) | CAM **U0T** (U0TXD) | straight, not crossed |
| **RX** (RX0 / RXD0 / GPIO3) | CAM **U0R** (U0RXD) | straight, not crossed |
| CAM **IO0** | CAM **GND** (any GND pin) | puts the camera in flash mode |

The pins are straight (TX→TX, RX→RX) because the DevKit's pins are labelled from its own chip's side, which is switched off. The USB chip talks straight through.

### 1B. ESP32-CAM RUNNING (normal use)

Remove the **IO0–GND**, **TX** and **RX** wires. Keep:

| From (DevKit) | To |
|---|---|
| EN | DevKit GND (keeps the DevKit quiet, saves power) |
| VIN | CAM 5V |
| GND | CAM GND |

Then plug the **DevKit's USB into the power bank** instead of the laptop. The camera streams on its own.

### 1C. NodeMCU sensor board (stays on the laptop USB)

All sensors on **3V3, never 5V** (5 V damages the RC522).

| Sensor | Sensor pin | NodeMCU pin |
|---|---|---|
| IR obstacle | VCC | 3V3 |
| | GND | G |
| | OUT | **D2** |
| DHT11 / DHT22 | + (VCC) | 3V3 |
| | − (GND) | G |
| | DATA / OUT | **D1** |
| RC522 RFID | 3.3V | 3V3 |
| | RST | 3V3 |
| | GND | G |
| | IRQ | (not connected) |
| | MISO | **D6** |
| | MOSI | **D7** |
| | SCK | **D5** |
| | SDA (SS) | **D8** |

- The NodeMCU has several 3V3 and G pins; use any of them. A small breadboard rail helps.
- A bare 4-pin DHT (no little PCB) needs a 10 kΩ resistor between DATA and 3V3. 3-pin modules have it built in.
- The DHT moved from D4 to **D1** compared with the old setup.

---

## 2. One-time preparation

1. **Hotspot.** On the iPhone, go to Settings → Personal Hotspot:
   - turn on **Allow Others to Join** and **Maximize Compatibility** (2.4 GHz; ESP boards can't see 5 GHz)
   - keep this screen open while boards connect, because iPhones hide the hotspot when idle
2. **Laptop on the same hotspot** (`param`).
3. **Arduino IDE:**
   - Boards Manager: **esp32** (installed: 3.3.7) and **esp8266** (installed: 3.1.2)
   - Library Manager: **MFRC522**, **DHT sensor library** (Adafruit), **Adafruit Unified Sensor** (all installed)
4. **Drivers.** If no COM port appears when you plug in a board, install the USB driver printed on its chip: CP210x or CH340.

---

## 3. Flash the camera (DevKit wiring 1A)

1. Wire as in **1A**, including IO0→GND, and plug the **DevKit** into the laptop by USB.
2. Arduino IDE: **File → Open** → `firmware/setup_v2/veridata_cam_v2/veridata_cam_v2.ino`.
3. Tools menu:
   - Board: **AI Thinker ESP32-CAM**
   - Port: the DevKit's COM port (the one that appears when you plug it in)
   - Upload Speed: **115200**
   - **Erase All Flash Before Sketch Upload: Enabled** (first time only; clears the old crash loop)
4. Click **Upload**. When the output shows `Connecting.....`, press the small **RST** button on the ESP32-CAM once.
5. Wait for `Writing at ... (100 %)` and then `Hard resetting via RTS pin...`.
6. **Remove the IO0–GND wire** (keep TX and RX for now).
7. Open **Tools → Serial Monitor** at **115200 baud** and press **RST** on the camera. Expected:
   ```
   Veridata ESP32-CAM (setup v2)
   sensor PID: 0x... 
   psram: yes
   camera OK
   joining Wi-Fi "param"......
   ==== READY ====
   Status: http://172.20.10.X/
   Photo:  http://172.20.10.X/capture
   Video:  http://172.20.10.X:81/stream
   ```
   Write down the **camera IP**. The red LED on the back blinks fast while joining Wi-Fi and stays **solid ON** when ready.
8. Set **Erase All Flash** back to **Disabled** for future uploads.

**Test now, before unplugging.** In the laptop browser:
- `http://<cam-ip>/` → text: `Veridata ESP32-CAM OK`
- `http://<cam-ip>/capture` → one photo (refresh = new photo)
- `http://<cam-ip>:81/stream` → live video

## 4. Move the camera to the power bank (wiring 1B)

1. Unplug the DevKit's USB from the laptop.
2. Remove the **TX** and **RX** wires. Keep EN→GND, VIN→5V and GND→GND.
3. Plug the DevKit's USB into the **power bank** and switch the power bank on.
4. Watch the camera's red LED: fast blink for a few seconds, then **solid ON**.
5. On the laptop, open `http://<cam-ip>/capture` again. It should work; the IP usually stays the same.
6. Leave `http://<cam-ip>:81/stream` open for 5 minutes and move the camera gently. The video should keep running. If it reboots, see Troubleshooting.

Some power banks switch off when the current draw is small. The camera on Wi-Fi draws ~150 mA, which keeps most of them awake. If yours shuts off after ~30 s, use a different port (some have a "low current" mode) or a different power bank.

## 5. Flash the sensor board (wiring 1C)

1. Wire the sensors as in **1C** and plug the **NodeMCU** into the laptop by USB.
2. **File → Open** → `firmware/setup_v2/veridata_sensors_v2/veridata_sensors_v2.ino`.
3. Tools:
   - Board: **NodeMCU 1.0 (ESP-12E Module)**
   - Port: the NodeMCU's COM port
   - Upload Speed: 115200 (or 921600)
   - Erase Flash: **All Flash Contents** (first time only, then back to "Only Sketch")
4. Click **Upload**. No buttons are needed; the NodeMCU resets itself.
5. Serial Monitor at **115200**. Press the NodeMCU's **RST** button. Expected:
   ```
   Veridata NodeMCU veridata-sensors-v2
   RC522: found (version 0x92)        <- 0x91/0x92/0x88 all fine
   Scanning Wi-Fi...
     param                    ch  6  -45 dBm
   Target network FOUND: param
   WiFi connecting to param
   ==== READY ====
   IP: 172.20.10.Y
   ```
   and every 5 s a status line:
   ```
   IR:clr | T:27.4 H:61.0 | RC522:ok | tags:0 | IP:172.20.10.Y
   ```
   Write down the **sensor IP**.

### Test each sensor (watch the Serial Monitor or open `http://<sensor-ip>/`)

| Test | Do | Expect |
|---|---|---|
| IR | Hold your hand 3–5 cm in front of the IR sensor | `IR:OBJ` and the IR module's own LED lights. Turn the small blue potentiometer if it never/always triggers |
| DHT | Wait 5 s; breathe on the sensor | `T:` and `H:` show numbers; humidity rises when you breathe on it |
| RC522 | Tap a card or key fob flat on the reader | Serial prints `RFID tag: 04A1B2C3`, `tags:` count goes up |
| JSON | Open `http://<sensor-ip>/sensors` | JSON with `ir`, `temp_c`, `humidity_pct`, `rfid` (the tag shows for 8 s after a tap) |

---

## 6. Connect to the Veridata app

1. Start the backend and the frontend as usual:
   ```powershell
   # terminal 1
   cd veridata\backend
   uvicorn app.main:app --port 8000
   # terminal 2
   cd veridata\web
   npm run dev
   ```
2. Open http://localhost:3000 → **Devices** → your device.
3. In **Connection (IPs change on hotspots)**, set:
   - Camera /capture URL: `http://<cam-ip>/capture`
   - Sensor board URL: `http://<sensor-ip>`

   Then click **Save URLs**. The stream URL is derived automatically.
4. Optional, for new devices: put the same values in `veridata/.env`:
   ```
   CAM_CAPTURE_URL=http://<cam-ip>/capture
   CAM_STREAM_URL=http://<cam-ip>:81/stream
   DEVICE_CONTROL_URL=http://<sensor-ip>
   ```
   and restart the backend.

## 7. End-to-end test in the app

1. **Capture & Upload** page, select the device:
   - the live view updates about twice a second (fps badge in the corner)
   - the tiles show **IR**, **Temperature**, **Humidity** and **Sensor board: online**
2. Put your hand in front of the IR sensor: the IR tile changes within about a second.
3. Tap an RFID card: the RFID panel marks the tag and it **stays marked** after you remove the card.
4. Click **Capture & sign**: a sample appears with the photo, the sensor readings, the RFID tag and a signed manifest.
5. Switch off the power bank: within a few seconds you should see "Rig camera is reconnecting" and a button to use the laptop camera. Switch it back on: the live view returns by itself in about 10–20 s.

## 8. Daily start / stop

**Start:**
1. Turn on the hotspot (screen open).
2. Power bank on (camera LED → solid).
3. Plug the NodeMCU into the laptop.
4. Start the backend, then the frontend.

**Stop:**
1. Ctrl+C the frontend and backend.
2. Power bank off.
3. Unplug the NodeMCU.

Nothing needs to be reflashed; Wi-Fi settings are compiled in, so the boards rejoin on their own.
If the iPhone gives a board a new IP, update it on the device page (step 6.3).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Upload: `Failed to connect ... Wrong boot mode` | camera not in flash mode | IO0 must be on GND, then press camera RST while `Connecting...` shows |
| Upload: `No serial data received` / `Invalid head of packet` | DevKit's chip is talking on the same wires | check **DevKit EN → GND**; TX→U0T, RX→U0R (straight); 115200 baud |
| `A fatal error occurred: The chip stopped responding` | power dip during flashing | use a short, good USB cable on a laptop port directly (no hub) |
| Serial shows `Brownout detector` or the camera keeps rebooting | weak 5 V | power bank instead of laptop USB; short thick wires on 5V/GND |
| `camera init attempt 3/3 failed` | ribbon cable loose | flip up the black latch, push the ribbon fully in (contacts toward the board), press the latch down |
| Red LED keeps fast-blinking; restarts every 30 s | can't find hotspot | open the iPhone hotspot screen; Maximize Compatibility ON; name must be exactly `param` |
| Garbage characters in Serial Monitor | wrong baud | set 115200 |
| `RC522: NOT found` | wiring | 3.3V and GND, SDA→D8, SCK→D5, MOSI→D7, MISO→D6; reseat the jumper wires |
| `T:null H:null` | DHT wiring | DATA on **D1**; + on 3V3; bare 4-pin DHT needs 10 kΩ DATA→3V3 |
| IR always `OBJ` or never | sensitivity | turn the potentiometer on the IR module slowly |
| App shows "Camera unreachable" but the browser URL works | wrong URL saved in the device | re-save the URLs on the device page; restart backend |
| Photo works, app tiles show "Sensor board offline" | NodeMCU IP changed | read the new IP from the Serial Monitor; update "Sensor board URL" |
