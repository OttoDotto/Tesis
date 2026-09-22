import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_TX,
    SOAPY_SDR_CF32,
    SOAPY_SDR_END_BURST
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
    ORIGEN_DATOS,
    LONGITUD_PN,
    TAPS_PN
)

from datos_utils import cargar_datos

from funciones_dsss import (
    generar_codigo_pn,
    ensanchar
)

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


# ============================================================
# CÓDIGO PN
# ============================================================

pn_bipolar = generar_codigo_pn(
    TAPS_PN,
    LONGITUD_PN
)


# ============================================================
# DSSS
# ============================================================

chips_dsss = ensanchar(
    bits_datos,
    pn_bipolar
)


# Convertimos los chips ±1 a bits 0/1
# para reutilizar el modulador BPSK
bits_chips = (
    (chips_dsss + 1) // 2
).astype(int)

bits_chips = "".join(
    str(int(bit))
    for bit in bits_chips
)


# ============================================================
# TRAMA
# ============================================================

BITS_TX = (
    PREAMBULO
    + bits_chips
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
print("TRANSMISOR DSSS-BPSK - DATOS REALES")
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
    "Bits originales:"
)

print(
    "".join(
        str(int(bit))
        for bit in bits_datos
    )
)

print()

print("DSSS")
print("--------------------------------------------")

print(
    f"Longitud PN : {LONGITUD_PN} chips"
)

print(
    f"Taps PN     : {TAPS_PN}"
)

print(
    f"Bits datos  : {len(bits_datos)}"
)

print(
    f"Chips DSSS  : {len(chips_dsss)}"
)

print()

print("TRAMA")
print("--------------------------------------------")

print(
    f"Preámbulo   : {len(PREAMBULO)} bits"
)

print(
    f"Datos DSSS  : {len(chips_dsss)} chips"
)

print(
    f"Guarda      : {len(GUARDA)} bits"
)

print(
    f"Total TX    : {len(BITS_TX)} símbolos"
)

print()

print(
    f"Muestras    : {len(senal)}"
)

print(
    f"Duración    : "
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

    # Cerramos la ráfaga explícitamente: enviamos un buffer
    # vacío con la flag END_BURST para que el USRP sepa que
    # no hay más datos y no intente sostener/repetir el
    # último bloque.
    sdr.writeStream(
        stream,
        [np.zeros(1, dtype=np.complex64)],
        1,
        flags=SOAPY_SDR_END_BURST
    )

    print()
    print("TX terminado.")

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