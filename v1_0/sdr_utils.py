"""
Utilidades para transmitir/recibir por SDR real usando SoapySDR (driver=uhd).
"""

import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_TX,
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32,
    SOAPY_SDR_END_BURST,
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
    sdr = SoapySDR.Device(args)

    sdr.setSampleRate(SOAPY_SDR_TX, canal, sample_rate)
    sdr.setFrequency(SOAPY_SDR_TX, canal, freq_hz)
    sdr.setGain(SOAPY_SDR_TX, canal, ganancia_db)
    sdr.setAntenna(SOAPY_SDR_TX, canal, antena)

    tx_stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [canal])
    sdr.activateStream(tx_stream)

    print(
        f"SDR TX abierto — {freq_hz/1e6:.3f} MHz, "
        f"{sample_rate/1e6:.3f} Msps, ganancia {ganancia_db} dB, antena {antena}"
    )

    return sdr, tx_stream


def transmitir_señal(
    sdr,
    tx_stream,
    señal_baseband,
    canal=0,
    timeout_us=1_000_000
):
    buffer_tx = np.ascontiguousarray(señal_baseband, dtype=np.complex64)

    resultado = sdr.writeStream(
        tx_stream,
        [buffer_tx],
        len(buffer_tx),
        flags=SOAPY_SDR_END_BURST,
        timeoutUs=timeout_us,
    )

    if resultado.ret != len(buffer_tx):
        print(
            f"TX SDR: se esperaban {len(buffer_tx)} muestras, "
            f"writeStream devolvió ret={resultado.ret}"
        )
        return False

    return True


def cerrar_sdr_tx(sdr, tx_stream):
    try:
        sdr.deactivateStream(tx_stream)
        sdr.closeStream(tx_stream)
        print("Stream TX cerrado.")
    except Exception as e:
        print(f"Error al cerrar stream TX: {e}")


# ============================================================
# RX
# ============================================================

def abrir_sdr_rx(
    args,
    canal,
    freq_hz,
    sample_rate,
    ganancia_db,
    antena="TX/RX"
):
    sdr = SoapySDR.Device(args)

    sdr.setSampleRate(SOAPY_SDR_RX, canal, sample_rate)
    sdr.setFrequency(SOAPY_SDR_RX, canal, freq_hz)
    sdr.setGain(SOAPY_SDR_RX, canal, ganancia_db)
    sdr.setAntenna(SOAPY_SDR_RX, canal, antena)

    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [canal])
    sdr.activateStream(rx_stream)

    print(
        f"SDR RX abierto — {freq_hz/1e6:.3f} MHz, "
        f"{sample_rate/1e6:.3f} Msps, ganancia {ganancia_db} dB, antena {antena}"
    )

    return sdr, rx_stream


def recibir_muestras(
    sdr,
    rx_stream,
    cantidad_muestras,
    timeout_us=500_000
):
    """
    Recibe muestras del buffer de SoapySDR.
    Devuelve un array de NumPy 1D (complex64). Devuelve array vacío si hay timeout.
    """
    buffer_rx = np.empty(cantidad_muestras, dtype=np.complex64)

    resultado = sdr.readStream(
        rx_stream,
        [buffer_rx],
        cantidad_muestras,
        timeoutUs=timeout_us,
    )

    if resultado.ret <= 0:
        return np.array([], dtype=np.complex64)

    return buffer_rx[:resultado.ret].copy()


def cerrar_sdr_rx(sdr, rx_stream):
    try:
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        print("Stream RX cerrado.")
    except Exception as e:
        print(f"Error al cerrar stream RX: {e}")