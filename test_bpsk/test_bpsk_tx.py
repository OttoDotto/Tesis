import numpy as np
import SoapySDR

from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32


# ============================================================
# CONFIGURACIÓN
# ============================================================

FREQ_CENTRAL = 920e6
SAMPLE_RATE = 1e6
GANANCIA_TX = 40

CANAL = 0
ANTENA = "TX/RX"

# Cada bit se mantiene durante esta cantidad de muestras
MUESTRAS_POR_BIT = 8

# Secuencia conocida
BITS = np.array(
    [
        1, 0, 1, 1,
        0, 0, 1, 0,
        1, 0, 0, 1,
        1, 1, 0, 0
    ],
    dtype=np.uint8
)

# Repeticiones de la secuencia
REPETICIONES = 100


# ============================================================
# CONFIGURAR SDR
# ============================================================

print("Abriendo SDR TX...")

sdr = SoapySDR.Device("driver=uhd")

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

tx_stream = sdr.setupStream(
    SOAPY_SDR_TX,
    SOAPY_SDR_CF32,
    [CANAL]
)

sdr.activateStream(tx_stream)


# ============================================================
# MOSTRAR CONFIGURACIÓN
# ============================================================

print()
print("=" * 60)
print("TX BPSK SIMPLE")
print("=" * 60)

print(f"Frecuencia RF : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate   : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia      : {GANANCIA_TX} dB")
print(f"Muestras/bit  : {MUESTRAS_POR_BIT}")
print(f"Bits          : {''.join(map(str, BITS))}")
print(f"Cantidad bits : {len(BITS)}")

print("=" * 60)


# ============================================================
# BPSK
# ============================================================

# 0 -> -1
# 1 -> +1

simbolos = 2 * BITS.astype(np.float32) - 1


# Repetir cada símbolo durante varias muestras

señal = np.repeat(
    simbolos,
    MUESTRAS_POR_BIT
)


# Convertir a señal compleja

señal = señal.astype(np.complex64)


# Repetir la secuencia completa varias veces

señal = np.tile(
    señal,
    REPETICIONES
)


print()
print(f"Muestras totales: {len(señal)}")
print(
    f"Duración: "
    f"{len(señal) / SAMPLE_RATE * 1000:.3f} ms"
)

print()
print("Secuencia BPSK:")
print(
    " ".join(
        "+" if bit == 1 else "-"
        for bit in BITS
    )
)

print()
print("Transmitiendo...")
print("Ctrl+C para detener.")
print()


# ============================================================
# TRANSMISIÓN CONTINUA
# ============================================================

try:

    while True:

        resultado = sdr.writeStream(
            tx_stream,
            [señal],
            len(señal),
            timeoutUs=1_000_000
        )

        if resultado.ret < 0:

            print(
                f"Error TX: {resultado.ret}"
            )

except KeyboardInterrupt:

    print()
    print("TX detenido.")


# ============================================================
# CERRAR
# ============================================================

sdr.deactivateStream(tx_stream)
sdr.closeStream(tx_stream)

print("SDR TX cerrado.")