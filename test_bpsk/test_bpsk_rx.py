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

MUESTRAS_POR_BIT = 8

BITS_ESPERADOS = np.array(
    [
        1, 0, 1, 1,
        0, 0, 1, 0,
        1, 0, 0, 1,
        1, 1, 0, 0
    ],
    dtype=np.uint8
)

CANTIDAD_MUESTRAS = 200000


# ============================================================
# CONFIGURAR SDR
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


# ============================================================
# MOSTRAR CONFIGURACIÓN
# ============================================================

print()
print("=" * 60)
print("RX BPSK SIMPLE")
print("=" * 60)

print(f"Frecuencia RF : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate   : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia      : {GANANCIA_RX} dB")
print(f"Muestras/bit  : {MUESTRAS_POR_BIT}")

print(
    f"Esperados     : "
    f"{''.join(map(str, BITS_ESPERADOS))}"
)

print("=" * 60)

print()
print("Esperando señal BPSK...")
print("Ctrl+C para detener.")
print()


# ============================================================
# BUFFER
# ============================================================

buffer_rx = np.empty(
    CANTIDAD_MUESTRAS,
    dtype=np.complex64
)


# ============================================================
# RECEPCIÓN
# ============================================================

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

        muestras = buffer_rx[:resultado.ret].copy()


        # ====================================================
        # BUSCAR SEÑAL
        # ====================================================

        potencia = np.abs(muestras)

        nivel_maximo = np.max(potencia)

        nivel_medio = np.mean(potencia)


        print(
            f"RX: "
            f"máximo={nivel_maximo:.4f} "
            f"| medio={nivel_medio:.4f}"
        )


        # ====================================================
        # BUSCAR LOS BITS
        # ====================================================

        cantidad_bits = len(BITS_ESPERADOS)

        muestras_necesarias = (
            cantidad_bits *
            MUESTRAS_POR_BIT
        )

        if len(muestras) < muestras_necesarias:

            continue


        # Tomamos las primeras muestras
        # por ahora, sin sincronización

        muestras_bits = muestras[
            :muestras_necesarias
        ]


        # Agrupar muestras correspondientes
        # a cada bit

        bloques = muestras_bits.reshape(
            cantidad_bits,
            MUESTRAS_POR_BIT
        )


        # Promedio complejo de cada bit

        simbolos_recibidos = np.mean(
            bloques,
            axis=1
        )


        # ====================================================
        # DECISIÓN BPSK
        # ====================================================

        bits_recibidos = (
            np.real(simbolos_recibidos) > 0
        ).astype(np.uint8)


        # ====================================================
        # MOSTRAR
        # ====================================================

        print()
        print("-" * 60)

        print(
            "Esperados : "
            + "".join(
                map(str, BITS_ESPERADOS)
            )
        )

        print(
            "Recibidos : "
            + "".join(
                map(str, bits_recibidos)
            )
        )


        errores = np.sum(
            bits_recibidos != BITS_ESPERADOS
        )


        print(
            f"Errores   : "
            f"{errores} / {cantidad_bits}"
        )


        if errores == 0:

            print()
            print("======================================")
            print("       BPSK RECIBIDO CORRECTAMENTE")
            print("======================================")
            print()

        else:

            print()
            print("Resultado: ERROR")
            print()


except KeyboardInterrupt:

    print()
    print("RX detenido.")


# ============================================================
# CERRAR
# ============================================================

sdr.deactivateStream(rx_stream)
sdr.closeStream(rx_stream)

print("SDR RX cerrado.")