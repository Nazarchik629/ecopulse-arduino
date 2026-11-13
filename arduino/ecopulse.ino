#include <DHT.h>

// Подключение DHT11/DHT22: DATA -> D2, VCC -> 5V, GND -> GND.
#define DHT_PIN 2
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);
const unsigned long intervalMs = 10000;
unsigned long lastRead = 0;

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  if (millis() - lastRead < intervalMs) return;
  lastRead = millis();

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("ERROR");
    return;
  }

  Serial.print(temperature, 1);
  Serial.print(',');
  Serial.println(humidity, 1);
}
