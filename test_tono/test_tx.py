import numpy as np
import SoapySDR

from SoapySDR import SOAPY_SDR_TX, SOAPY_SDR_CF32


# ============================================================
# CONFIGURACIÓN
# ============================================================

FREQ_CENTRAL = 920e6
SAMPLE_RATE = 1e6
GANANCIA_TX = 50

FRECUENCIA_TONO = 100e3

CANAL = 0
ANTENA = "TX/RX"

CANTIDAD_MUESTRAS = 100000


# ============================================================
# SDR
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


print()
print("=" * 50)
print("TX SIMPLE")
print("=" * 50)
print(f"Frecuencia RF : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate   : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Tono          : {FRECUENCIA_TONO / 1e3:.1f} kHz")
print(f"Ganancia      : {GANANCIA_TX} dB")
print("=" * 50)


# ============================================================
# GENERAR TONO
# ============================================================

t = np.arange(CANTIDAD_MUESTRAS) / SAMPLE_RATE

señal = np.exp(
    1j * 2 * np.pi * FRECUENCIA_TONO * t
)

señal = señal.astype(np.complex64)


# ============================================================
# TRANSMISIÓN CONTINUA
# ============================================================

print()
print("Transmitiendo tono...")
print("Ctrl+C para detener.")
print()

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