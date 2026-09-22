import random
import struct


# ============================================================
# ESTRUCTURA DEL PAQUETE DE DATOS
# ============================================================

FORMATO_PAQUETE = "<ffH"

TAMAÑO_PAQUETE_BYTES = struct.calcsize(FORMATO_PAQUETE)


# ============================================================
# GENERACIÓN DE PAQUETES
# ============================================================

def generar_paquete_ejemplo(aleatorio=False):
    """
    Genera un paquete de sensores de prueba.

    Si aleatorio=False:
        utiliza valores fijos.

    Si aleatorio=True:
        genera valores aleatorios dentro de rangos definidos.
    """

    if aleatorio:
        temperatura = random.uniform(15.0, 35.0)
        humedad = random.uniform(30.0, 80.0)
        luz = random.randint(0, 1023)

    else:
        temperatura = 23.5
        humedad = 60.2
        luz = 512

    return struct.pack(
        FORMATO_PAQUETE,
        temperatura,
        humedad,
        luz
    )


# ============================================================
# INTERPRETACIÓN DEL PAQUETE
# ============================================================

def interpretar_paquete(datos):
    """
    Interpreta los bytes recibidos según la estructura
    definida para el paquete.
    """

    if len(datos) != TAMAÑO_PAQUETE_BYTES:
        raise ValueError(
            f"Paquete inválido: se esperaban "
            f"{TAMAÑO_PAQUETE_BYTES} bytes, "
            f"se recibieron {len(datos)}"
        )

    return struct.unpack(
        FORMATO_PAQUETE,
        datos
    )


# ============================================================
# REPRESENTACIÓN LEGIBLE
# ============================================================

def describir_paquete(datos):
    """
    Devuelve una representación legible del paquete.
    """

    temperatura, humedad, luz = interpretar_paquete(datos)

    return (
        f"Temperatura={temperatura:.2f} °C | "
        f"Humedad={humedad:.2f} % | "
        f"Luz={luz}"
    )
