import numpy as np
import SoapySDR

from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32


# ============================================================
# CONFIGURACIÓN
# ============================================================

FREQ_CENTRAL = 920e6
SAMPLE_RATE = 1e6
GANANCIA_RX = 40

CANAL = 0
ANTENA = "TX/RX"

CANTIDAD_MUESTRAS = 200000


# ============================================================
# SDR
# ============================================================

print("Abriendo SDR RX...")

sdr = SoapySDR.Device("driver=uhd")

sdr.setSampleRate(
    SOAPY_SDR_RX,
    CANAL,
    SAMPLE_RATE
)

sdr.setFrequency(
    SOAPY_SDR_RX,
    CANAL,
    FREQ_CENTRAL
)

sdr.setGain(
    SOAPY_SDR_RX,
    CANAL,
    GANANCIA_RX
)

sdr.setAntenna(
    SOAPY_SDR_RX,
    CANAL,
    ANTENA
)

rx_stream = sdr.setupStream(
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32,
    [CANAL]
)

sdr.activateStream(rx_stream)


print()
print("=" * 50)
print("RX SIMPLE")
print("=" * 50)
print(f"Frecuencia RF : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate   : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia      : {GANANCIA_RX} dB")
print("=" * 50)

print()
print("Esperando señal...")
print("Ctrl+C para detener.")
print()


# ============================================================
# RECEPCIÓN
# ============================================================

buffer_rx = np.empty(
    CANTIDAD_MUESTRAS,
    dtype=np.complex64
)


try:

    while True:

        resultado = sdr.readStream(
            rx_stream,
            [buffer_rx],
            CANTIDAD_MUESTRAS,
            timeoutUs=1_000_000
        )

        if resultado.ret <= 0:
            print(
                f"Error RX: {resultado.ret}"
            )
            continue

        muestras = buffer_rx[:resultado.ret]

        # ----------------------------------------------------
        # FFT
        # ----------------------------------------------------

        ventana = np.hanning(len(muestras))

        espectro = np.fft.fftshift(
            np.fft.fft(
                muestras * ventana
            )
        )

        frecuencias = np.fft.fftshift(
            np.fft.fftfreq(
                len(muestras),
                1 / SAMPLE_RATE
            )
        )

        magnitud = np.abs(espectro)

        # Buscar pico

        indice_pico = np.argmax(magnitud)

        frecuencia_pico = frecuencias[indice_pico]

        pico = magnitud[indice_pico]

        potencia = 20 * np.log10(
            pico + 1e-12
        )

        # ----------------------------------------------------
        # Mostrar resultado
        # ----------------------------------------------------

        print(
            f"Pico: "
            f"{frecuencia_pico / 1e3:+.1f} kHz "
            f"| "
            f"Nivel: {potencia:.1f} dB"
        )


except KeyboardInterrupt:

    print()
    print("RX detenido.")


# ============================================================
# CERRAR
# ============================================================

sdr.deactivateStream(rx_stream)
sdr.closeStream(rx_stream)

print("SDR RX cerrado.")