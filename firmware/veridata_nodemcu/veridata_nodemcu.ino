/*
  Veridata sensor board: NodeMCU 1.0 (ESP-12E), esp8266 core 3.1.x
  Arduino IDE board: "NodeMCU 1.0 (ESP-12E Module)", Serial Monitor 115200.

  Libraries (Library Manager):
    - MFRC522 (GithubCommunity)
    - DHT sensor library (Adafruit) + Adafruit Unified Sensor

  Wiring (matches board.md):
    IR OUT      -> D2 (GPIO4), active-LOW = object, VCC 3V3
    RC522 SDA   -> D8 (GPIO15)   SCK -> D5   MOSI -> D7   MISO -> D6
          RST   -> 3V3 (tied high; firmware does a soft reset)   3.3V only
    DHT DATA    -> D4 (GPIO2), + -> 3V3, - -> GND
    LED         -> GPIO16 (on-board, active-LOW), blinks on every HTTP request
    ESP32-CAM   -> power only (runs CameraWebServer separately)

  HTTP API on port 80 (JSON, CORS *). The Veridata backend polls this:
    GET /sensors -> {"distance_cm":null,"ir":true,"servo_deg":null,"temp_c":27.4,"humidity_pct":61.0,
                     "rfid":{"uid":"04A1B2C3","seen_ms_ago":1200}|null,"rfid_reader":"ok",
                     "dht_type":"DHT22","uptime_ms":123456,"rssi":-58,"fw":"veridata-nodemcu-0.1.0","board":"esp8266"}
    GET /         -> plain-text status page (open it in a browser to test)

  No /pubkey or /sign: this board has no on-device signing, so the backend registers it as a
  "dev-software" device (the platform holds the key, and the UI labels it that way).
*/
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <SPI.h>
#include <MFRC522.h>
#include <DHT.h>

// ---------- EDIT THESE ----------
#define WIFI_SSID     "YOUR_WIFI"        // same 2.4 GHz network as the ESP32-CAM and laptop
#define WIFI_PASSWORD "YOUR_PASSWORD"
// --------------------------------
#define FW_VERSION "veridata-nodemcu-0.1.0"

#define PIN_IR    4    // D2
#define PIN_SS    15   // D8
#define PIN_DHT   2    // D4
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
  b += "\"distance_cm\":null,";                       // no ultrasonic wired yet
  b += "\"ir\":" + String(irObject() ? "true" : "false") + ",";
  b += "\"servo_deg\":null,";                         // no servo on this rig
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

  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);           // faster HTTP responses
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.print("\nIP: "); Serial.println(WiFi.localIP());
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
