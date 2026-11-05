/*
  Veridata main board — ESP32 DevKit (Arduino core 2.0.x)

  Sensors/actuators:  HC-SR04 ultrasonic, IR obstacle sensor, SG90 servo (camera pan),
                      MFRC522 RFID reader (SPI).
  Identity:           ECDSA P-256 key generated on first boot, private key kept in NVS
                      (never leaves the board). Signs capture-manifest digests (ES256).
  The ESP32-CAM runs the stock CameraWebServer sketch (/capture, :81/stream) on the same Wi-Fi.

  HTTP API (port 80, JSON, CORS *):
    GET /sensors           {distance_cm, ir, servo_deg, rfid:{uid,seen_ms_ago}|null, uptime_ms, fw}
    GET /servo?deg=0..180  move servo
    GET /pubkey            {"pubkey":"04<X><Y>"}
    GET /sign?digest=<64 hex>   {"sig":"<r><s>"}   (ECDSA P-256 over the given SHA-256 digest)

  Libraries: MFRC522 (miguelbalboa). No other external libs.
  Status: written for core 2.0.x; NOT yet compiled or validated on hardware — see docs/HARDWARE.md.

  Wiring (see docs/HARDWARE.md):
    HC-SR04  TRIG 26, ECHO 25 (via 1k/2k divider to 3.3V level)
    IR       OUT 27 (most modules are active-LOW)
    Servo    signal 13 (power servo from 5V, common GND)
    RC522    SDA/SS 5, SCK 18, MOSI 23, MISO 19, RST 22, 3.3V only
*/
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <SPI.h>
#include <MFRC522.h>
#include "mbedtls/ecdsa.h"
#include "mbedtls/ecp.h"
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/entropy.h"

// ----------- configuration -----------
#define WIFI_SSID     "YOUR_WIFI"
#define WIFI_PASSWORD "YOUR_PASSWORD"
#define FW_VERSION    "veridata-main-0.1.0"

#define PIN_TRIG   26
#define PIN_ECHO   25
#define PIN_IR     27
#define IR_ACTIVE_LOW 1
#define PIN_SERVO  13
#define PIN_RC_SS  5
#define PIN_RC_RST 22

WebServer server(80);
Preferences prefs;
MFRC522 rfid(PIN_RC_SS, PIN_RC_RST);

mbedtls_ecp_group grp;
mbedtls_mpi priv;
mbedtls_ecp_point pub;
mbedtls_ctr_drbg_context drbg;
mbedtls_entropy_context entropy;
String pubHex;

float distanceCm = -1;
int servoDeg = 90;
String lastUid = "";
unsigned long lastUidAt = 0;
unsigned long lastSonar = 0;

// ----------- helpers -----------
static String toHex(const uint8_t* b, size_t n) {
  static const char* h = "0123456789abcdef";
  String s; s.reserve(n * 2);
  for (size_t i = 0; i < n; i++) { s += h[b[i] >> 4]; s += h[b[i] & 15]; }
  return s;
}
static bool fromHex(const String& s, uint8_t* out, size_t n) {
  if (s.length() != n * 2) return false;
  for (size_t i = 0; i < n; i++) {
    char c[3] = { s[2 * i], s[2 * i + 1], 0 };
    char* end; long v = strtol(c, &end, 16);
    if (*end) return false;
    out[i] = (uint8_t)v;
  }
  return true;
}
static void sendJson(int code, const String& body) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(code, "application/json", body);
}

// ----------- servo (LEDC, 50 Hz) -----------
void servoWrite(int deg) {
  deg = constrain(deg, 0, 180);
  servoDeg = deg;
  uint32_t us = 500 + (uint32_t)deg * 2000 / 180;   // 500–2500 µs
  ledcWrite(0, (us * 65535UL) / 20000UL);           // 16-bit duty over 20 ms
}

// ----------- ultrasonic (median of 5) -----------
float readSonarOnce() {
  digitalWrite(PIN_TRIG, LOW); delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long d = pulseIn(PIN_ECHO, HIGH, 25000);   // ~4 m max
  return d == 0 ? -1 : d / 58.0f;
}
void updateSonar() {
  float v[5]; int n = 0;
  for (int i = 0; i < 5; i++) { float x = readSonarOnce(); if (x > 0) v[n++] = x; delay(8); }
  if (!n) { distanceCm = -1; return; }
  for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) if (v[j] < v[i]) { float t = v[i]; v[i] = v[j]; v[j] = t; }
  distanceCm = v[n / 2];
}

// ----------- RFID -----------
void pollRfid() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  lastUid = toHex(rfid.uid.uidByte, rfid.uid.size);
  lastUid.toUpperCase();
  lastUidAt = millis();
  rfid.PICC_HaltA();
}

// ----------- device key (ECDSA P-256) -----------
bool initKey() {
  mbedtls_ecp_group_init(&grp); mbedtls_mpi_init(&priv); mbedtls_ecp_point_init(&pub);
  mbedtls_ctr_drbg_init(&drbg); mbedtls_entropy_init(&entropy);
  const char* pers = "veridata-device";
  if (mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &entropy, (const uint8_t*)pers, strlen(pers))) return false;
  if (mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1)) return false;

  uint8_t d[32];
  prefs.begin("vdkey", false);
  if (prefs.getBytesLength("d") == 32) {
    prefs.getBytes("d", d, 32);
    mbedtls_mpi_read_binary(&priv, d, 32);
    mbedtls_ecp_mul(&grp, &pub, &priv, &grp.G, mbedtls_ctr_drbg_random, &drbg);
  } else {
    if (mbedtls_ecp_gen_keypair(&grp, &priv, &pub, mbedtls_ctr_drbg_random, &drbg)) return false;
    mbedtls_mpi_write_binary(&priv, d, 32);
    prefs.putBytes("d", d, 32);   // NVS; enable flash encryption for production
  }
  memset(d, 0, sizeof d);
  prefs.end();

  uint8_t q[65]; size_t qlen = 0;
  mbedtls_ecp_point_write_binary(&grp, &pub, MBEDTLS_ECP_PF_UNCOMPRESSED, &qlen, q, sizeof q);
  pubHex = toHex(q, qlen);
  return qlen == 65;
}

bool signDigest(const uint8_t digest[32], String& out) {
  mbedtls_mpi r, s; mbedtls_mpi_init(&r); mbedtls_mpi_init(&s);
  int rc = mbedtls_ecdsa_sign(&grp, &r, &s, &priv, digest, 32, mbedtls_ctr_drbg_random, &drbg);
  if (rc == 0) {
    uint8_t rb[32], sb[32];
    mbedtls_mpi_write_binary(&r, rb, 32);
    mbedtls_mpi_write_binary(&s, sb, 32);
    out = toHex(rb, 32) + toHex(sb, 32);
  }
  mbedtls_mpi_free(&r); mbedtls_mpi_free(&s);
  return rc == 0;
}

// ----------- HTTP handlers -----------
void hSensors() {
  bool irRaw = digitalRead(PIN_IR);
  bool ir = IR_ACTIVE_LOW ? !irRaw : irRaw;
  String rf = "null";
  if (lastUid.length() && millis() - lastUidAt < 8000)
    rf = "{\"uid\":\"" + lastUid + "\",\"seen_ms_ago\":" + String(millis() - lastUidAt) + "}";
  String body = "{\"distance_cm\":" + (distanceCm < 0 ? String("null") : String(distanceCm, 1)) +
                ",\"ir\":" + (ir ? "true" : "false") +
                ",\"servo_deg\":" + String(servoDeg) +
                ",\"rfid\":" + rf +
                ",\"uptime_ms\":" + String(millis()) +
                ",\"rssi\":" + String(WiFi.RSSI()) +
                ",\"fw\":\"" FW_VERSION "\"}";
  sendJson(200, body);
}
void hServo() {
  if (!server.hasArg("deg")) return sendJson(400, "{\"error\":\"deg required\"}");
  servoWrite(server.arg("deg").toInt());
  sendJson(200, "{\"ok\":true,\"servo_deg\":" + String(servoDeg) + "}");
}
void hPubkey() { sendJson(200, "{\"pubkey\":\"" + pubHex + "\",\"alg\":\"ES256\"}"); }
void hSign() {
  uint8_t dg[32];
  if (!server.hasArg("digest") || !fromHex(server.arg("digest"), dg, 32)) return sendJson(400, "{\"error\":\"digest must be 64 hex chars\"}");
  String sig;
  if (!signDigest(dg, sig)) return sendJson(500, "{\"error\":\"sign failed\"}");
  sendJson(200, "{\"sig\":\"" + sig + "\"}");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT); pinMode(PIN_IR, INPUT);
  ledcSetup(0, 50, 16); ledcAttachPin(PIN_SERVO, 0); servoWrite(90);
  SPI.begin(18, 19, 23, PIN_RC_SS); rfid.PCD_Init();
  Serial.println(initKey() ? "key ok: " + pubHex : "KEY INIT FAILED");

  WiFi.mode(WIFI_STA); WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.print("\nIP: "); Serial.println(WiFi.localIP());

  server.on("/sensors", hSensors);
  server.on("/servo", hServo);
  server.on("/pubkey", hPubkey);
  server.on("/sign", hSign);
  server.begin();
}

void loop() {
  server.handleClient();
  pollRfid();
  if (millis() - lastSonar > 300) { updateSonar(); lastSonar = millis(); }
  if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
}
