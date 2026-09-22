import random
import struct

# ============================================================
# ESTRUCTURA: DATOS DEL SENSOR (sin numerar)
# ============================================================
FORMATO_DATOS = "<ffH"
TAMAÑO_DATOS_BYTES = struct.calcsize(FORMATO_DATOS)

# ============================================================
# ESTRUCTURA: PAQUETE COMPLETO (número de secuencia + datos)
# ============================================================
FORMATO_PAQUETE = "<I" + FORMATO_DATOS[1:]   # "<IffH"
TAMAÑO_PAQUETE_BYTES = struct.calcsize(FORMATO_PAQUETE)

# ============================================================
# RANGOS VÁLIDOS
# ============================================================
TEMPERATURA_MIN = 15.0
TEMPERATURA_MAX = 35.0
HUMEDAD_MIN = 30.0
HUMEDAD_MAX = 80.0
LUZ_MIN = 500
LUZ_MAX = 600

# ============================================================
# GENERACIÓN DE DATOS DEL SENSOR
# ============================================================
def generar_datos_ejemplo(aleatorio=False):
    if aleatorio:
        temperatura = random.uniform(TEMPERATURA_MIN, TEMPERATURA_MAX)
        humedad = random.uniform(HUMEDAD_MIN, HUMEDAD_MAX)
        luz = random.randint(LUZ_MIN, LUZ_MAX)
    else:
        temperatura, humedad, luz = 23.5, 60.2, 512
    return struct.pack(FORMATO_DATOS, temperatura, humedad, luz)

# ============================================================
# ARMADO DEL PAQUETE (agrega el número de secuencia)
# ============================================================
def armar_paquete(numero_secuencia, datos_sensor):
    temperatura, humedad, luz = struct.unpack(FORMATO_DATOS, datos_sensor)
    return struct.pack(FORMATO_PAQUETE, numero_secuencia, temperatura, humedad, luz)

# ============================================================
# INTERPRETACIÓN
# ============================================================
def interpretar_paquete(datos):
    if len(datos) != TAMAÑO_PAQUETE_BYTES:
        raise ValueError(
            f"Paquete inválido: se esperaban {TAMAÑO_PAQUETE_BYTES} bytes, "
            f"se recibieron {len(datos)}"
        )
    return struct.unpack(FORMATO_PAQUETE, datos)   # numero, temperatura, humedad, luz

# ============================================================
# REPRESENTACIÓN LEGIBLE
# ============================================================
def describir_paquete(datos):
    numero, temperatura, humedad, luz = interpretar_paquete(datos)
    return (
        f"Nro={numero:06d} | Temperatura={temperatura:.2f} °C | "
        f"Humedad={humedad:.2f} % | Luz={luz}"
    )