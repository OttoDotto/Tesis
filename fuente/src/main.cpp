#include <Arduino.h>

#pragma pack(push, 1)

struct PaqueteSensores {
    float temperatura;
    float humedad;
    uint16_t luz;
};

#pragma pack(pop)

const unsigned long PERIODO_PAQUETE = 500;

unsigned long ultimoPaquete = 0;

void setup()
{
    Serial.begin(9600);
}

void loop()
{
    unsigned long ahora = millis();

    if (ahora - ultimoPaquete >= PERIODO_PAQUETE)
    {
        ultimoPaquete = ahora;

        PaqueteSensores paquete;

        paquete.temperatura = 23.5;
        paquete.humedad = 60.2;
        paquete.luz = 512;

        Serial.write((uint8_t*)&paquete, sizeof(paquete));
    }
}