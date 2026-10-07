import random
import struct
import zlib

# ============================================================
# ESTRUCTURA DEL PAQUETE DE DATOS (UGV + CRC)
# ============================================================

# Añadimos un entero de 4 bytes al final ('I') para el CRC-32
FORMATO_PAQUETE = "<ffffHI"

TAMAÑO_PAQUETE_BYTES = struct.calcsize(
    FORMATO_PAQUETE
)

# ============================================================
# GENERACIÓN DE PAQUETES
# ============================================================

def generar_paquete_ejemplo(aleatorio=False):

    if aleatorio:
        latitud = random.uniform(-34.5000, -34.7000)
        longitud = random.uniform(-58.3000, -58.5000)
        velocidad = random.uniform(0.0, 45.0)
        rumbo = random.uniform(0.0, 359.9)
        bateria = random.randint(10, 100)
    else:
        latitud = -34.6037
        longitud = -58.3816
        velocidad = 15.5
        rumbo = 90.0
        bateria = 85

    # 1. Empaquetamos los datos sin el CRC (poniendo 0 temporalmente en el campo CRC)
    datos_sin_crc = struct.pack("<ffffH", latitud, longitud, velocidad, rumbo, bateria)
    
    # 2. Calculamos el CRC-32 de los datos
    checksum = zlib.crc32(datos_sin_crc) & 0xFFFFFFFF

    # 3. Retornamos el paquete completo incluyendo el CRC al final
    return struct.pack(FORMATO_PAQUETE, latitud, longitud, velocidad, rumbo, bateria, checksum)

# ============================================================
# INTERPRETACIÓN Y VALIDACIÓN CRC
# ============================================================

def interpretar_paquete(datos):
    if len(datos) != TAMAÑO_PAQUETE_BYTES:
        raise ValueError(
            f"Paquete invalido: se esperaban "
            f"{TAMAÑO_PAQUETE_BYTES} bytes, "
            f"se recibieron {len(datos)}"
        )

    # Desempaquetamos incluyendo el CRC recibido
    latitud, longitud, velocidad, rumbo, bateria, crc_recibido = struct.unpack(
        FORMATO_PAQUETE,
        datos
    )

    # Reconstruimos los datos base (sin el CRC) para recalcular y verificar
    datos_sin_crc = struct.pack("<ffffH", latitud, longitud, velocidad, rumbo, bateria)
    crc_calculado = zlib.crc32(datos_sin_crc) & 0xFFFFFFFF

    # Si el CRC no coincide, la trama esta corrupta (falso positivo o ruido)
    if crc_calculado != crc_recibido:
        raise ValueError("Error de CRC: la trama esta corrupta o es ruido")

    return latitud, longitud, velocidad, rumbo, bateria

# ============================================================
# REPRESENTACIÓN LEGIBLE
# ============================================================

def describir_paquete(datos):
    latitud, longitud, velocidad, rumbo, bateria = (
        interpretar_paquete(datos)
    )

    return (
        f"LAT={latitud:.4f} | "
        f"LON={longitud:.4f} | "
        f"VEL={velocidad:.1f} km/h | "
        f"RUMBO={rumbo:.1f} deg | "
        f"BAT={bateria}%"
    )