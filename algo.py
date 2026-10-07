#!/usr/bin/env python3
import binascii
import random
import socket
import struct
import time

FORMATO_PAQUETE = "<ffffH"
TAM_PAYLOAD = struct.calcsize(FORMATO_PAQUETE)   # 18 bytes
PROB_ERROR = 0.20   # probabilidad de que el canal dane la trama

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def crc16(datos: bytes) -> int:
    # CRC-16/CCITT-FALSE. Si en tu codigo usas otra variante, reemplaza esta funcion.
    return binascii.crc_hqx(datos, 0xFFFF)


def armar_trama(payload: bytes) -> bytes:
    """Lo que hace el TX: payload + CRC16."""
    return payload + struct.pack("<H", crc16(payload))


def canal_ruidoso(trama: bytes):
    """Simula el canal: con probabilidad PROB_ERROR daña la trama."""
    if random.random() >= PROB_ERROR:
        return trama, "sin errores"
    if random.random() < 0.5:
        n = random.randint(1, len(trama) - 1)
        return trama[:n], f"truncada a {n} bytes"
    datos = bytearray(trama)
    pos = random.sample(range(len(datos)), random.randint(1, 3))
    for p in pos:
        datos[p] ^= random.randint(1, 255)
    return bytes(datos), f"bytes alterados en {sorted(pos)}"


def verificar_trama(trama: bytes):
    """Lo que hace tu RX: devuelve el payload si es valido, None si lo descarta."""
    if len(trama) != TAM_PAYLOAD + 2:
        return None
    payload, crc_rx = trama[:-2], struct.unpack("<H", trama[-2:])[0]
    return payload if crc16(payload) == crc_rx else None


bateria = 100
descartados = 0
while True:
    payload = struct.pack(FORMATO_PAQUETE,
                          -34.6037,   # latitud
                          -58.3816,   # longitud
                          12.5,       # velocidad km/h
                          90.0,       # rumbo
                          bateria)    # bateria %

    trama_rx, canal = canal_ruidoso(armar_trama(payload))
    valido = verificar_trama(trama_rx)

    if valido is None:
        descartados += 1
        print(f"bateria={bateria} | canal: {canal} -> DESCARTADO (total {descartados})")
    else:
        sock.sendto(valido, ("127.0.0.1", 5005))
        print(f"bateria={bateria} | canal: {canal} -> enviado a pantalla")

    bateria = max(0, bateria - 5)
    time.sleep(1)