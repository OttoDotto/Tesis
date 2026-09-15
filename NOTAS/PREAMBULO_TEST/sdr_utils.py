"""
Utilidades para transmitir/recibir por SDR real usando SoapySDR.

Usamos SoapySDR (con driver=uhd) en vez de la API de UHD
directamente.
"""

import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_TX,
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32,
    SOAPY_SDR_END_BURST,
    SOAPY_SDR_HAS_TIME,
)


# ============================================================
# TX
# ============================================================

def abrir_sdr_tx(
    args,
    canal,
    freq_hz,
    sample_rate,
    ganancia_db,
    antena="TX/RX"
):
    """
    Abre el dispositivo y configura + activa el stream de TX.
    """

    sdr = SoapySDR.Device(args)

    sdr.setSampleRate(
        SOAPY_SDR_TX,
        canal,
        sample_rate
    )

    sdr.setFrequency(
        SOAPY_SDR_TX,
        canal,
        freq_hz
    )

    sdr.setGain(
        SOAPY_SDR_TX,
        canal,
        ganancia_db
    )

    sdr.setAntenna(
        SOAPY_SDR_TX,
        canal,
        antena
    )

    tx_stream = sdr.setupStream(
        SOAPY_SDR_TX,
        SOAPY_SDR_CF32,
        [canal]
    )

    sdr.activateStream(
        tx_stream
    )

    print(
        f"SDR TX abierto — "
        f"{freq_hz/1e6:.3f} MHz, "
        f"{sample_rate/1e6:.3f} Msps, "
        f"ganancia {ganancia_db} dB, "
        f"antena {antena}"
    )

    return sdr, tx_stream


def transmitir_señal(
    sdr,
    tx_stream,
    señal_baseband,
    canal=0,
    timeout_us=1_000_000
):
    """
    Transmite una ráfaga completa.
    """

    buffer_tx = np.ascontiguousarray(
        señal_baseband,
        dtype=np.complex64
    )

    resultado = sdr.writeStream(
        tx_stream,
        [buffer_tx],
        len(buffer_tx),
        flags=SOAPY_SDR_END_BURST,
        timeoutUs=timeout_us,
    )

    if resultado.ret != len(buffer_tx):

        print(
            f"TX SDR: se esperaban "
            f"{len(buffer_tx)} muestras, "
            f"writeStream devolvió "
            f"ret={resultado.ret}"
        )

        return False

    return True


def cerrar_sdr_tx(
    sdr,
    tx_stream
):
    """
    Cierra el stream TX.
    """

    try:

        sdr.deactivateStream(
            tx_stream
        )

        sdr.closeStream(
            tx_stream
        )

        print(
            "Stream TX cerrado."
        )

    except Exception as e:

        print(
            f"Error al cerrar "
            f"stream TX: {e}"
        )


# ============================================================
# RX
# ============================================================

def abrir_sdr_rx(
    args,
    canal,
    freq_hz,
    sample_rate,
    ganancia_db,
    antena="RX2"
):
    """
    Abre el dispositivo y configura + activa el stream de RX.
    """

    sdr = SoapySDR.Device(args)

    sdr.setSampleRate(
        SOAPY_SDR_RX,
        canal,
        sample_rate
    )

    sdr.setFrequency(
        SOAPY_SDR_RX,
        canal,
        freq_hz
    )

    sdr.setGain(
        SOAPY_SDR_RX,
        canal,
        ganancia_db
    )

    sdr.setAntenna(
        SOAPY_SDR_RX,
        canal,
        antena
    )

    rx_stream = sdr.setupStream(
        SOAPY_SDR_RX,
        SOAPY_SDR_CF32,
        [canal]
    )

    sdr.activateStream(
        rx_stream
    )

    print(
        f"SDR RX abierto — "
        f"{freq_hz/1e6:.3f} MHz, "
        f"{sample_rate/1e6:.3f} Msps, "
        f"ganancia {ganancia_db} dB, "
        f"antena {antena}"
    )

    return sdr, rx_stream


def recibir_muestras(
    sdr,
    rx_stream,
    cantidad_muestras,
    canal=0,
    timeout_us=1_000_000
):
    """
    Recibe una cantidad determinada de muestras IQ.

    Devuelve:
        muestras : np.ndarray complex64
        cantidad : cantidad realmente recibida
        flags    : flags devueltos por SoapySDR
    """

    buffer_rx = np.empty(
        cantidad_muestras,
        dtype=np.complex64
    )

    resultado = sdr.readStream(
        rx_stream,
        [buffer_rx],
        cantidad_muestras,
        timeoutUs=timeout_us,
    )

    if resultado.ret < 0:

        print(
            f"RX SDR: error en readStream: "
            f"{resultado.ret}"
        )

        return None, resultado.ret, resultado.flags

    muestras = buffer_rx[
        :resultado.ret
    ].copy()

    return (
        muestras,
        resultado.ret,
        resultado.flags
    )


def cerrar_sdr_rx(
    sdr,
    rx_stream
):
    """
    Cierra el stream RX.
    """

    try:

        sdr.deactivateStream(
            rx_stream
        )

        sdr.closeStream(
            rx_stream
        )

        print(
            "Stream RX cerrado."
        )

    except Exception as e:

        print(
            f"Error al cerrar "
            f"stream RX: {e}"
        )