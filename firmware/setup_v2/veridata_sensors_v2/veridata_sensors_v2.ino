/*
  Veridata sensor board, setup v2: NodeMCU 1.0 (ESP8266) on the laptop's USB, with IR + DHT + RC522.
  Arduino IDE board: "NodeMCU 1.0 (ESP-12E Module)", Serial Monitor 115200.

  Libraries (Library Manager):
    - MFRC522 (GithubCommunity)
    - DHT sensor library (Adafruit) + Adafruit Unified Sensor

  Wiring (all sensors on 3V3, never 5V):
    IR     VCC -> 3V3   GND -> G   OUT -> D2 (GPIO4)   active-LOW = object
    DHT    +   -> 3V3   -   -> G   DATA -> D1 (GPIO5)  (bare 4-pin DHT: 10k DATA->3V3)
    RC522  3.3V -> 3V3  RST -> 3V3  GND -> G  IRQ -> nc
           MISO -> D6   MOSI -> D7   SCK -> D5   SDA -> D8
    LED    on-board (GPIO16), blinks on every HTTP request

  HTTP API on port 80 (JSON, CORS *), polled by the Veridata backend over Wi-Fi:
    GET /sensors -> {"ir":true,"temp_c":27.4,"humidity_pct":61.0,"rfid":{"uid":"04A1B2C3","seen_ms_ago":1200}|null,
                     "rfid_reader":"ok","tags_read":3,"dht_type":"DHT11","uptime_ms":123456,"rssi":-58,"fw":"...","board":"esp8266"}
    GET /         -> plain-text status page (open it in a browser to test)

  No on-device signing: the backend registers it as a "dev-software" device and the UI labels it so.
*/
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <SPI.h>
#include <MFRC522.h>
#include <DHT.h>

// ---------- EDIT THESE ----------
// Wi-Fi credentials live in secrets.h next to this file (gitignored). Copy secrets.example.h to
// secrets.h and fill it in; without it the placeholders below are used.
#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef WIFI_SSID
#define WIFI_SSID     "YOUR_WIFI"        // 2.4 GHz, same network as the laptop
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_PASSWORD"
#endif
// --------------------------------
#define FW_VERSION "veridata-sensors-v2"

#define PIN_IR    4    // D2
#define PIN_SS    15   // D8
#define PIN_DHT   5    // D1 (not a boot pin, unlike D4)
#define PIN_LED   16   // D0, active-LOW
#define IR_ACTIVE_LOW 1

ESP8266WebServer server(80);
MFRC522 rfid(PIN_SS, UINT8_MAX);       // UINT8_MAX = RST pin not used (tied to 3V3)

DHT dht22(PIN_DHT, DHT22);
DHT dht11(PIN_DHT, DHT11);
int dhtType = 0;                       // 0 = unknown, 22 or 11 once a valid read happens
float tempC = NAN, humidity = NAN;
unsigned long lastDht = 0;

bool readerOk = false;
unsigned long lastReaderCheck = 0;
String lastUid = "";
unsigned long lastUidAt = 0;
unsigned long tagsRead = 0;

// ---------- RFID ----------
bool checkReader() {
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  return v != 0x00 && v != 0xFF;
}

void initReader() {
  rfid.PCD_Init();
  delay(5);
  readerOk = checkReader();
  Serial.printf("RC522: %s (version 0x%02X)\n", readerOk ? "found" : "NOT found",
                rfid.PCD_ReadRegister(MFRC522::VersionReg));
}

void pollRfid() {
  if (!readerOk) return;
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  lastUid = uid;
  lastUidAt = millis();
  tagsRead++;
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  Serial.println("RFID tag: " + uid);
}

// ---------- DHT (auto-detects DHT22 vs DHT11) ----------
void pollDht() {
  if (millis() - lastDht < 2500) return;      // DHT22 needs >= 2 s between reads
  lastDht = millis();
  float t, h;
  if (dhtType == 0 || dhtType == 22) {
    t = dht22.readTemperature(); h = dht22.readHumidity();
    if (!isnan(t) && !isnan(h)) { dhtType = 22; tempC = t; humidity = h; return; }
  }
  if (dhtType == 0 || dhtType == 11) {
    t = dht11.readTemperature(); h = dht11.readHumidity();
    if (!isnan(t) && !isnan(h)) { dhtType = 11; tempC = t; humidity = h; return; }
  }
  tempC = NAN; humidity = NAN;                 // keep the last type, report "no reading"
}

// ---------- HTTP ----------
String num(float v, int d) { return isnan(v) ? String("null") : String(v, d); }

bool irObject() {
  bool raw = digitalRead(PIN_IR);
  return IR_ACTIVE_LOW ? !raw : raw;
}

void blink() { digitalWrite(PIN_LED, LOW); delay(2); digitalWrite(PIN_LED, HIGH); }

void hSensors() {
  blink();
  String rf = "null";
  if (lastUid.length() && millis() - lastUidAt < 8000)
    rf = "{\"uid\":\"" + lastUid + "\",\"seen_ms_ago\":" + String(millis() - lastUidAt) + "}";
  String b = "{";
  b += "\"ir\":" + String(irObject() ? "true" : "false") + ",";
  b += "\"temp_c\":" + num(tempC, 1) + ",";
  b += "\"humidity_pct\":" + num(humidity, 1) + ",";
  b += "\"rfid\":" + rf + ",";
  b += "\"rfid_reader\":\"" + String(readerOk ? "ok" : "missing") + "\",";
  b += "\"tags_read\":" + String(tagsRead) + ",";
  b += "\"dht_type\":" + String(dhtType ? "\"DHT" + String(dhtType) + "\"" : "null") + ",";
  b += "\"uptime_ms\":" + String(millis()) + ",";
  b += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  b += "\"fw\":\"" FW_VERSION "\",\"board\":\"esp8266\"}";
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", b);
}

void hRoot() {
  String s = "Veridata sensor board (" FW_VERSION ")\n";
  s += "IP: " + WiFi.localIP().toString() + "\n";
  s += "IR: " + String(irObject() ? "OBJECT" : "clear") + "\n";
  s += "DHT: " + (isnan(tempC) ? String("no valid reading") : String(tempC, 1) + " C, " + String(humidity, 1) + " %") + "\n";
  s += "RC522: " + String(readerOk ? "ok" : "missing") + ", tags read: " + String(tagsRead) + ", last: " + (lastUid.length() ? lastUid : "-") + "\n";
  s += "\nJSON: /sensors\n";
  server.send(200, "text/plain", s);
}

void hNotFound() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(404, "application/json", "{\"error\":\"not found\"}");
}

// ---------- setup / loop ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n\nVeridata NodeMCU " FW_VERSION);
  pinMode(PIN_LED, OUTPUT); digitalWrite(PIN_LED, HIGH);
  pinMode(PIN_IR, INPUT);

  SPI.begin();
  initReader();
  dht22.begin();
  dht11.begin();

  WiFi.persistent(false);                       // never rewrite Wi-Fi config in flash
  WiFi.setAutoReconnect(true);                  // rejoin the hotspot by itself if it drops
  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);           // faster HTTP responses
  WiFi.disconnect();
  delay(100);

  // Show which networks the board can see, so a missing or 5 GHz hotspot is obvious.
  Serial.println("Scanning Wi-Fi...");
  int n = WiFi.scanNetworks();
  bool seen = false;
  for (int i = 0; i < n; i++) {
    Serial.printf("  %-24s ch %2d  %d dBm\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i));
    if (WiFi.SSID(i) == WIFI_SSID) seen = true;
  }
  Serial.println(seen ? "Target network FOUND: " WIFI_SSID
                      : "Target network NOT visible: " WIFI_SSID " (check the name; hotspot must be 2.4 GHz / Maximize Compatibility)");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("WiFi connecting to " WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(2000);
    wl_status_t st = WiFi.status();
    const char* why = st == WL_NO_SSID_AVAIL ? "network not found" :
                      st == WL_WRONG_PASSWORD ? "WRONG PASSWORD" :
                      st == WL_CONNECT_FAILED ? "connect failed" :
                      st == WL_IDLE_STATUS ? "idle" :
                      st == WL_DISCONNECTED ? "still trying" : "other";
    Serial.printf("  ...not connected yet (status %d: %s, %lus)\n", (int)st, why, (millis() - t0) / 1000);
    if (millis() - t0 > 30000) {                 // start over every 30 s
      WiFi.disconnect(); delay(200);
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      t0 = millis();
    }
  }
  Serial.println("==== READY ====");
  Serial.print("IP: "); Serial.println(WiFi.localIP());
  Serial.println("Open http://" + WiFi.localIP().toString() + "/sensors");

  server.on("/", hRoot);
  server.on("/sensors", hSensors);
  server.onNotFound(hNotFound);
  server.begin();
}

void loop() {
  server.handleClient();
  pollRfid();
  pollDht();
  if (millis() - lastReaderCheck > 5000) {      // RC522 has been flaky: re-check and re-init
    lastReaderCheck = millis();
    if (!checkReader()) initReader(); else readerOk = true;
  }
  static unsigned long lastLog = 0;
  if (millis() - lastLog > 5000) {
    lastLog = millis();
    Serial.printf("IR:%s | T:%s H:%s | RC522:%s | tags:%lu | IP:%s\n",
                  irObject() ? "OBJ" : "clr", num(tempC, 1).c_str(), num(humidity, 1).c_str(),
                  readerOk ? "ok" : "missing", tagsRead, WiFi.localIP().toString().c_str());
  }
  yield();
}
