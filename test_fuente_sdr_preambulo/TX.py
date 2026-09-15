import time
import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_TX,
    SOAPY_SDR_CF32
)

from config import (
    FREQ_CENTRAL,
    SAMPLE_RATE,
    CANAL_SDR,
    ANTENA_TX,
    GANANCIA_TX,
    MUESTRAS_POR_BIT,
    PREAMBULO,
    GUARDA,
    ORIGEN_DATOS
)

from datos_utils import cargar_datos

from paquete import (
    describir_paquete
)


def generar_bpsk(bits):

    simbolos = np.array(
        [
            1.0 if bit == "1" else -1.0
            for bit in bits
        ],
        dtype=np.float32
    )

    return np.repeat(
        simbolos,
        MUESTRAS_POR_BIT
    )


# ============================================================
# DATOS
# ============================================================

datos = cargar_datos(
    origen=ORIGEN_DATOS
)

bits_datos = np.unpackbits(
    np.frombuffer(
        datos,
        dtype=np.uint8
    )
).astype(int)

bits_datos = "".join(
    str(int(bit))
    for bit in bits_datos
)


# ============================================================
# TRAMA
# ============================================================

BITS_TX = (
    PREAMBULO
    + bits_datos
    + GUARDA
)


# ============================================================
# SDR
# ============================================================

sdr = SoapySDR.Device(
    "driver=uhd"
)

sdr.setSampleRate(
    SOAPY_SDR_TX,
    CANAL_SDR,
    SAMPLE_RATE
)

sdr.setFrequency(
    SOAPY_SDR_TX,
    CANAL_SDR,
    FREQ_CENTRAL
)

sdr.setGain(
    SOAPY_SDR_TX,
    CANAL_SDR,
    GANANCIA_TX
)

sdr.setAntenna(
    SOAPY_SDR_TX,
    CANAL_SDR,
    ANTENA_TX
)

stream = sdr.setupStream(
    SOAPY_SDR_TX,
    SOAPY_SDR_CF32
)

sdr.activateStream(
    stream
)


# ============================================================
# SEÑAL BPSK
# ============================================================

senal = generar_bpsk(
    BITS_TX
).astype(
    np.complex64
)


# ============================================================
# INFORMACIÓN
# ============================================================

print()
print("============================================")
print("TRANSMISOR BPSK - DATOS REALES")
print("============================================")

print(
    f"Frecuencia : "
    f"{FREQ_CENTRAL / 1e6:.3f} MHz"
)

print(
    f"Sample rate: "
    f"{SAMPLE_RATE / 1e6:.3f} Msps"
)

print(
    f"Ganancia   : {GANANCIA_TX}"
)

print(
    f"Antena     : {ANTENA_TX}"
)

print()

print(
    f"Origen datos: {ORIGEN_DATOS}"
)

print()

print("DATOS A TRANSMITIR")
print("--------------------------------------------")

print(
    describir_paquete(
        datos
    )
)

print(
    f"Bytes: {datos.hex()}"
)

print(
    f"Bits : {bits_datos}"
)

print()

print(
    f"Preámbulo  : {len(PREAMBULO)} bits"
)

print(
    f"Datos      : {len(bits_datos)} bits"
)

print(
    f"Guarda     : {len(GUARDA)} bits"
)

print(
    f"Total TX   : {len(BITS_TX)} bits"
)

print()

print(
    f"Muestras   : {len(senal)}"
)

print(
    f"Duración   : "
    f"{len(senal) / SAMPLE_RATE * 1e3:.3f} ms"
)

print()

print("Transmitiendo un solo paquete...")
print()


# ============================================================
# TRANSMISIÓN
# ============================================================

try:

    offset = 0

    while offset < len(senal):

        resultado = sdr.writeStream(
            stream,
            [senal[offset:]],
            len(senal) - offset
        )

        if resultado.ret < 0:

            print(
                f"Error TX: {resultado.ret}"
            )

            break

        offset += resultado.ret

    print(
        f"Paquete transmitido: "
        f"{offset} muestras"
    )

    print()
    print("TX terminado.")
    print("Presioná Ctrl+C para salir.")

    while True:
        time.sleep(1)

except KeyboardInterrupt:

    print()
    print("TX detenido.")

finally:

    sdr.deactivateStream(
        stream
    )

    sdr.closeStream(
        stream
    )