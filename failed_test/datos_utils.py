import numpy as np
import serial

from paquete import (
    generar_paquete_ejemplo,
    TAMAÑO_PAQUETE_BYTES
)


def cargar_bits_datos(origen="ejemplo", n_bits=8, conexion=None):
    """
    Obtiene los datos desde la fuente seleccionada
    y los convierte a bits.
    """

    if origen == "ejemplo":
        datos = generar_paquete_ejemplo(aleatorio=False)

    elif origen == "aleatorio":
        datos = generar_paquete_ejemplo(aleatorio=True)

    elif origen == "serial":

        if conexion is None:
            raise ValueError(
                "Necesitás pasar una conexión serial "
                "(parámetro conexion)"
            )

        datos = leer_datos_serial(
            conexion,
            TAMAÑO_PAQUETE_BYTES
        )

    else:
        raise ValueError(
            f"Origen desconocido: {origen}"
        )

    bits = np.unpackbits(
        np.frombuffer(datos, dtype=np.uint8)
    ).astype(int)

    return bits


def abrir_puerto_serial(puerto, baudrate=9600, timeout=2):

    return serial.Serial(
        puerto,
        baudrate,
        timeout=timeout
    )


def leer_datos_serial(ser, n_bytes):

    datos = ser.read(n_bytes)

    if len(datos) < n_bytes:
        raise TimeoutError(
            f"Paquete incompleto recibido del serial: "
            f"{len(datos)}/{n_bytes} bytes"
        )

    return datos