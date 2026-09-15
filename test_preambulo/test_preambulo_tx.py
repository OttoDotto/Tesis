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
    CANAL,
    ANTENA,
    GANANCIA_TX,
    MUESTRAS_POR_BIT,
    PREAMBULO,
    DATOS,
    GUARDA
)


# ============================================================
# GENERAR BPSK
# ============================================================

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
# TRAMA TRANSMITIDA
# ============================================================

BITS_TX = (
    PREAMBULO
    + DATOS
    + GUARDA
)


# ============================================================
# CONFIGURAR SDR
# ============================================================

sdr = SoapySDR.Device(
    "driver=uhd"
)

sdr.setSampleRate(
    SOAPY_SDR_TX,
    CANAL,
    SAMPLE_RATE
)

sdr.setFrequency(
    SOAPY_SDR_TX,
    CANAL,
    FREQ_CENTRAL
)

sdr.setGain(
    SOAPY_SDR_TX,
    CANAL,
    GANANCIA_TX
)

sdr.setAntenna(
    SOAPY_SDR_TX,
    CANAL,
    ANTENA
)

stream = sdr.setupStream(
    SOAPY_SDR_TX,
    SOAPY_SDR_CF32
)

sdr.activateStream(
    stream
)


# ============================================================
# GENERAR SEÑAL
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
print("TRANSMISOR BPSK")
print("============================================")

print(
    f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz"
)

print(
    f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps"
)

print(
    f"Ganancia   : {GANANCIA_TX}"
)

print(
    f"Antena     : {ANTENA}"
)

print()

print(
    f"Preámbulo : {len(PREAMBULO)} bits"
)

print(
    f"Datos     : {len(DATOS)} bits"
)

print(
    f"Guarda    : {len(GUARDA)} bits"
)

print(
    f"Total TX  : {len(BITS_TX)} bits"
)

print()

print(
    f"Preámbulo: {PREAMBULO}"
)

print(
    f"Datos    : {DATOS}"
)

print(
    f"Guarda   : {GUARDA}"
)

print()

print(
    f"Muestras : {len(senal)}"
)

print(
    f"Duración : "
    f"{len(senal) / SAMPLE_RATE * 1e6:.1f} us"
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
        f"Paquete transmitido: {offset} muestras"
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

    sdr.deactivateStream(stream)
    sdr.closeStream(stream)