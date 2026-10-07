'''
Define la estructura y los datos orientados a telemetría táctica (UGV).
'''
import random
import struct

# ============================================================
# ESTRUCTURA DEL PAQUETE DE DATOS (UGV)
# ============================================================

FORMATO_PAQUETE = "<ffffH"
TAMAÑO_PAQUETE_BYTES = struct.calcsize(FORMATO_PAQUETE)

# En el aire viaja: payload + CRC16 (2 bytes)
TAMAÑO_CRC_BYTES = 2
TAMAÑO_TRAMA_BYTES = TAMAÑO_PAQUETE_BYTES + TAMAÑO_CRC_BYTES

# ============================================================
# CRC16-CCITT (poly 0x1021, init 0xFFFF)
# ============================================================

def crc16_ccitt(datos: bytes, inicial: int = 0xFFFF) -> int:
    crc = inicial
    for byte in datos:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def agregar_crc(payload: bytes) -> bytes:
    return payload + crc16_ccitt(payload).to_bytes(2, "big")

def verificar_crc(trama: bytes):
    """Devuelve el payload si la trama es válida; None si el CRC no cierra."""
    if len(trama) != TAMAÑO_TRAMA_BYTES:
        return None
    payload, crc_rx = trama[:-2], int.from_bytes(trama[-2:], "big")
    return payload if crc16_ccitt(payload) == crc_rx else None

# ============================================================
# GENERACION DE PAQUETES
# ============================================================

def generar_paquete_ejemplo(aleatorio=False):
    if aleatorio:
        latitud = random.uniform(-34.5000, -34.7000)
        longitud = random.uniform(-58.3000, -58.5000)
        velocidad = random.uniform(10.0, 45.0)
        rumbo = random.uniform(10.0, 90.0)
        bateria = random.randint(10, 90)
    else:
        latitud = -34.6037
        longitud = -58.3816
        velocidad = 15.5
        rumbo = 90.0
        bateria = 85

    return struct.pack(FORMATO_PAQUETE, latitud, longitud, velocidad, rumbo, bateria)

# ============================================================
# INTERPRETACION
# ============================================================

def interpretar_paquete(datos):
    if len(datos) != TAMAÑO_PAQUETE_BYTES:
        raise ValueError(
            f"Paquete invalido: se esperaban {TAMAÑO_PAQUETE_BYTES} bytes, "
            f"se recibieron {len(datos)}"
        )
    return struct.unpack(FORMATO_PAQUETE, datos)


def describir_paquete(datos):
    latitud, longitud, velocidad, rumbo, bateria = interpretar_paquete(datos)
    return (
        f"LAT={latitud:.4f} | LON={longitud:.4f} | "
        f"VEL={velocidad:.1f} km/h | RUMBO={rumbo:.1f} deg | BAT={bateria}%"
    )
