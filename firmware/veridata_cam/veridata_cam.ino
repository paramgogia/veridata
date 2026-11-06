/*
 * Veridata camera: ESP32-CAM (AI-Thinker) serving
 *   http://<ip>/capture       one JPEG   (polled by the Veridata backend for live view + captures)
 *   http://<ip>:81/stream     MJPEG video
 *
 * Arduino IDE: Board "AI Thinker ESP32-CAM", Upload Speed 115200, Serial Monitor 115200.
 * Wi-Fi: put WIFI_SSID / WIFI_PASSWORD in secrets.h next to this file (gitignored; copy
 * secrets.example.h), or edit the fallback lines below.
 *
 * Robustness for weak 5 V supplies and software-JPEG sensors (GC2145):
 *   - brownout reset disabled, lower Wi-Fi TX power, 10 MHz camera clock
 *   - HTTP server purges idle sockets (LRU) so polling clients can't exhaust it
 *   - bigger handler stack for software JPEG conversion
 *   - reboots itself if Wi-Fi or the camera stops working
 *
 * Anyone on your Wi-Fi can open these URLs: use a network you trust.
 */
#include <WiFi.h>
#include <esp_camera.h>
#include <esp_http_server.h>
#include <img_converters.h>
#include "soc/soc.h"           // brownout detector registers
#include "soc/rtc_cntl_reg.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef WIFI_SSID
#define WIFI_SSID     "YOUR_WIFI"        // 2.4 GHz, same network as the laptop
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_PASSWORD"
#endif

#define STREAM_BOUNDARY "\r\n--frame\r\n"
SemaphoreHandle_t cameraLock;
bool rawMode = false;  // true when the sensor can't output JPEG (GC2145, OV7670...): convert on the board

// Gives a JPEG for a frame. In raw mode it converts, and *owned says the caller must free() it.
bool frameToJpeg(camera_fb_t *frame, uint8_t **buf, size_t *len, bool *owned) {
  if (!rawMode) {
    *buf = frame->buf;
    *len = frame->len;
    *owned = false;
    return true;
  }
  *owned = true;
  return frame2jpg(frame, 80, buf, len);
}

esp_err_t captureHandler(httpd_req_t *req) {
  if (xSemaphoreTake(cameraLock, pdMS_TO_TICKS(3000)) != pdTRUE) return httpd_resp_send_500(req);
  if (!rawMode) {  // JPEG sensors keep 2 buffers: drop the possibly-old one (raw mode has 1)
    camera_fb_t *stale = esp_camera_fb_get();
    if (stale) esp_camera_fb_return(stale);
  }
  camera_fb_t *frame = esp_camera_fb_get();
  esp_err_t result;
  uint8_t *jpg = nullptr;
  size_t jpgLen = 0;
  bool owned = false;
  if (frame && frameToJpeg(frame, &jpg, &jpgLen, &owned)) {
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    result = httpd_resp_send(req, (const char *)jpg, jpgLen);
    if (owned) free(jpg);
    esp_camera_fb_return(frame);
  } else if (frame) {
    Serial.println("JPEG conversion failed");
    esp_camera_fb_return(frame);
    result = httpd_resp_send_500(req);
  } else {
    Serial.println("camera returned no frame");
    result = httpd_resp_send_500(req);
  }
  xSemaphoreGive(cameraLock);
  return result;
}

esp_err_t streamHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  char header[64];
  esp_err_t result = ESP_OK;
  while (result == ESP_OK) {
    if (xSemaphoreTake(cameraLock, pdMS_TO_TICKS(3000)) != pdTRUE) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame) {
      uint8_t *jpg = nullptr;
      size_t jpgLen = 0;
      bool owned = false;
      if (frameToJpeg(frame, &jpg, &jpgLen, &owned)) {
        int headerLength = snprintf(header, sizeof(header), "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (unsigned)jpgLen);
        result = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (result == ESP_OK) result = httpd_resp_send_chunk(req, header, headerLength);
        if (result == ESP_OK) result = httpd_resp_send_chunk(req, (const char *)jpg, jpgLen);
        if (owned) free(jpg);
      }
      esp_camera_fb_return(frame);
    }
    xSemaphoreGive(cameraLock);
    vTaskDelay(pdMS_TO_TICKS(rawMode ? 100 : 1));  // lets photo requests in; eases load in raw mode
  }
  return result;
}

// Power-cycles the sensor through its PWDN pin: un-sticks a sensor left hung by a power dip.
void resetSensor() {
  pinMode(32, OUTPUT);
  digitalWrite(32, HIGH);
  delay(100);
  digitalWrite(32, LOW);
  delay(150);
}

esp_err_t rootHandler(httpd_req_t *req) {
  char body[220];
  snprintf(body, sizeof(body), "Veridata ESP32-CAM OK\nmode: %s\nuptime: %lus\nrssi: %d dBm\nphoto: /capture   video: :81/stream\n",
           rawMode ? "raw RGB565 -> JPEG (320x240)" : "JPEG", millis() / 1000, WiFi.RSSI());
  httpd_resp_set_type(req, "text/plain");
  return httpd_resp_send(req, body, strlen(body));
}

bool startCamera() {
  camera_config_t config = {};
  // AI-Thinker pin map.
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.pin_xclk = 0;
  config.pin_sccb_sda = 26;
  config.pin_sccb_scl = 27;
  config.pin_d7 = 35;
  config.pin_d6 = 34;
  config.pin_d5 = 39;
  config.pin_d4 = 36;
  config.pin_d3 = 21;
  config.pin_d2 = 19;
  config.pin_d1 = 18;
  config.pin_d0 = 5;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_pclk = 22;
  config.xclk_freq_hz = 10000000;  // 10 MHz: less current and heat, plenty for QVGA
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.grab_mode = CAMERA_GRAB_LATEST;
  bool psram = psramFound();
  config.fb_count = psram ? 2 : 1;
  config.fb_location = psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  esp_err_t err = esp_camera_init(&config);
  if (err == ESP_ERR_NOT_SUPPORTED) {
    // 0x106: the sensor can't make JPEG. Take raw RGB565 and convert on the board instead.
    Serial.println("sensor has no JPEG: switching to raw RGB565 + software JPEG (320x240)");
    esp_camera_deinit();
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAMESIZE_QVGA;  // 320x240: raw frames are big
    config.fb_count = 1;
    err = esp_camera_init(&config);
    rawMode = (err == ESP_OK);
  }
  if (err == ESP_OK) {
    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) Serial.printf("sensor PID: 0x%02x (0x26=OV2640, 0x2145=GC2145, 0x76=OV7670, 0x77=OV7725)\n", sensor->id.PID);
  }
  Serial.printf("psram: %s\n", psram ? "yes" : "NO (expect low quality or failures)");
  if (err != ESP_OK) Serial.printf("camera FAILED, error 0x%x. Check the ribbon cable and the board choice in Tools.\n", err);
  return err == ESP_OK;
}

void setup() {
  // Wi-Fi start-up draws 300+ mA spikes; on a weak 5 V feed the brownout detector resets the board
  // in a loop. Disabling it is a workaround: a proper 5 V >= 1 A supply is the real fix.
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);
  delay(300);
  pinMode(4, OUTPUT);  // flash LED stays off
  digitalWrite(4, LOW);
  Serial.println("\nVeridata ESP32-CAM");
  cameraLock = xSemaphoreCreateMutex();
  bool camOk = false;
  for (int attempt = 1; attempt <= 3 && !camOk; attempt++) {
    resetSensor();
    camOk = startCamera();
    if (!camOk) {
      Serial.printf("camera init attempt %d/3 failed\n", attempt);
      esp_camera_deinit();
      delay(500);
    }
  }
  if (!camOk) {
    Serial.println("camera not detected: reseat the ribbon cable (latch closed) and check 5 V power. Restarting in 5 s...");
    delay(5000);
    ESP.restart();
  }
  Serial.println("camera OK");

  WiFi.persistent(false);  // never write Wi-Fi config to flash (NVS): avoids crashes on a damaged NVS
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);  // smaller current spikes on weak 5 V supplies
  WiFi.setSleep(false);
  Serial.printf("joining Wi-Fi \"%s\"", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - t0 > 30000) {  // hotspot hidden/asleep: start over instead of waiting forever
      Serial.println("\nno Wi-Fi after 30 s (keep the hotspot screen open): restarting");
      delay(200);
      ESP.restart();
    }
  }
  String ip = WiFi.localIP().toString();
  Serial.printf("\n==== READY ====\nStatus: http://%s/\nPhoto:  http://%s/capture\nVideo:  http://%s:81/stream\n", ip.c_str(), ip.c_str(), ip.c_str());

  // Video occupies its server for as long as it runs, so photos get their own server.
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.stack_size = 8192;          // software JPEG conversion needs more than the 4 KB default
  config.lru_purge_enable = true;    // drop the oldest idle socket instead of refusing new clients
  config.max_open_sockets = 5;
  config.recv_wait_timeout = 5;
  config.send_wait_timeout = 5;
  httpd_handle_t photoServer = nullptr, videoServer = nullptr;
  httpd_uri_t capture = {};
  capture.uri = "/capture";
  capture.method = HTTP_GET;
  capture.handler = captureHandler;
  httpd_uri_t root = {};
  root.uri = "/";
  root.method = HTTP_GET;
  root.handler = rootHandler;
  if (httpd_start(&photoServer, &config) == ESP_OK) {
    httpd_register_uri_handler(photoServer, &capture);
    httpd_register_uri_handler(photoServer, &root);
  }

  config.server_port = 81;
  config.ctrl_port += 1;
  config.max_open_sockets = 2;
  httpd_uri_t stream = {};
  stream.uri = "/stream";
  stream.method = HTTP_GET;
  stream.handler = streamHandler;
  if (httpd_start(&videoServer, &config) == ESP_OK) httpd_register_uri_handler(videoServer, &stream);
}

int wifiFailures = 0;
int cameraFailures = 0;
unsigned long lastSelfTest = 0;

void loop() {
  // hotspots drop clients now and then: rejoin automatically (same IP is usually reassigned)
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi lost, reconnecting...");
    WiFi.reconnect();
    for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) delay(500);
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("back online: http://%s/capture\n", WiFi.localIP().toString().c_str());
      wifiFailures = 0;
    } else if (++wifiFailures >= 3) {
      Serial.println("Wi-Fi still down after 3 tries: restarting");
      delay(200);
      ESP.restart();
    }
  }
  // Self-heal: every 20 s check the camera still delivers a frame. After a power dip the sensor
  // can hang while the board stays up; 3 failed checks in a row reboot it.
  if (millis() - lastSelfTest > 20000) {
    lastSelfTest = millis();
    if (xSemaphoreTake(cameraLock, pdMS_TO_TICKS(2000)) == pdTRUE) {
      camera_fb_t *f = esp_camera_fb_get();
      if (f) { esp_camera_fb_return(f); cameraFailures = 0; }
      else cameraFailures++;
      xSemaphoreGive(cameraLock);
    } else {
      cameraFailures++;  // lock stuck for 2 s: a handler is hung
    }
    if (cameraFailures >= 3) {
      Serial.println("camera not responding: restarting");
      delay(200);
      ESP.restart();
    }
  }
  delay(1000);
}
