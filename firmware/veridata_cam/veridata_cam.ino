/*
 * Veridata camera: ESP32-CAM serving /capture (JPEG) and :81/stream (MJPEG) for the Veridata backend.
 * Register these URLs in the app as the device's CAM still URL and MJPEG stream.
 * Board: AI Thinker ESP32-CAM. Upload it through the ESP32, as in firmware/arduino/README.md.
 *
 * To see the IP address: after uploading, keep the wires but remove the GPIO 0 link, open the
 * Serial Monitor at 115200, and press the CAM's RST button.
 *
 * PASS: both of these work in a browser:
 *   http://<ip>/capture        one photo
 *   http://<ip>:81/stream      live video
 *
 * AI on top of it:
 *   python ai_detect.py --source http://<ip>/capture
 *   python ai_ask.py    --source http://<ip>/capture --question "What is in front of you?"
 *
 * Anyone on your Wi-Fi can view these two addresses, so use this sketch for testing or on a
 * network you trust.
 */
#include <WiFi.h>
#include <esp_camera.h>
#include <esp_http_server.h>
#include <img_converters.h>
#include "soc/soc.h"           // brownout detector registers
#include "soc/rtc_cntl_reg.h"

// ---------- CHANGE THESE ----------
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
#define WIFI_PASS WIFI_PASSWORD

#define STREAM_BOUNDARY "\r\n--frame\r\n"
SemaphoreHandle_t cameraLock;
bool rawMode = false;  // true when the sensor can't output JPEG (OV7670/OV7725): we convert on the board

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
  camera_fb_t *stale = esp_camera_fb_get();  // the first frame can be old
  if (stale) esp_camera_fb_return(stale);
  camera_fb_t *frame = esp_camera_fb_get();
  esp_err_t result;
  uint8_t *jpg = nullptr;
  size_t jpgLen = 0;
  bool owned = false;
  if (frame && frameToJpeg(frame, &jpg, &jpgLen, &owned)) {
    httpd_resp_set_type(req, "image/jpeg");
    result = httpd_resp_send(req, (const char *)jpg, jpgLen);
    Serial.printf("photo sent: %u bytes\n", (unsigned)jpgLen);
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
    if (xSemaphoreTake(cameraLock, pdMS_TO_TICKS(3000)) != pdTRUE) continue;
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
    vTaskDelay(1);  // lets a waiting photo request take the camera
  }
  return result;
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
  config.xclk_freq_hz = 20000000;
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
    Serial.println("sensor has no JPEG: switching to raw RGB565 + software JPEG (small frames, slower)");
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
  if (err != ESP_OK) Serial.printf("camera FAILED, error 0x%x. Check the ribbon cable, and the board choice in the Tools menu.\n", err);
  return err == ESP_OK;
}

void setup() {
  // The CAM's Wi-Fi start-up draws ~300+ mA spikes; on a weak 5V feed the brownout detector
  // resets the board in a loop. Disabling it is a workaround: a proper 5V >= 1 A supply is the real fix.
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);
  delay(300);
  pinMode(4, OUTPUT);  // flash LED stays off
  digitalWrite(4, LOW);
  Serial.println("\nTEST 4: ESP32-CAM");
  cameraLock = xSemaphoreCreateMutex();
  if (!startCamera()) return;
  Serial.println("camera OK");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);  // smaller current spikes: avoids brownout resets on weak 5V supplies
  WiFi.setSleep(false);
  Serial.print("joining Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  String ip = WiFi.localIP().toString();
  Serial.printf("\nPhoto: http://%s/capture\nVideo: http://%s:81/stream\n", ip.c_str(), ip.c_str());

  // Video occupies its server for as long as it runs, so photos get their own server.
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  httpd_handle_t photoServer = nullptr, videoServer = nullptr;
  httpd_uri_t capture = {};
  capture.uri = "/capture";
  capture.method = HTTP_GET;
  capture.handler = captureHandler;
  if (httpd_start(&photoServer, &config) == ESP_OK) httpd_register_uri_handler(photoServer, &capture);

  config.server_port = 81;
  config.ctrl_port += 1;
  httpd_uri_t stream = {};
  stream.uri = "/stream";
  stream.method = HTTP_GET;
  stream.handler = streamHandler;
  if (httpd_start(&videoServer, &config) == ESP_OK) httpd_register_uri_handler(videoServer, &stream);
}

void loop() {
  // hotspots drop clients now and then: rejoin automatically (same IP is usually reassigned)
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi lost, reconnecting...");
    WiFi.reconnect();
    for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) delay(500);
    if (WiFi.status() == WL_CONNECTED) Serial.printf("back online: http://%s/capture\n", WiFi.localIP().toString().c_str());
  }
  delay(1000);
}
