import time
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
    armar_paquete, 
    describir_paquete
)

# ============================================================
# CONFIGURACIÓN DE TRANSMISIÓN
# ============================================================

INTERVALO_PAQUETES = 0.5


# ============================================================
# MODULACIÓN BPSK
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
# CÓDIGO PN
# ============================================================

pn_bipolar = generar_codigo_pn(
    TAPS_PN,
    LONGITUD_PN
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
# INFORMACIÓN
# ============================================================

print()
print("============================================")
print("TRANSMISOR DSSS-BPSK - DATOS CONTINUOS")
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

print(
    f"Origen datos: {ORIGEN_DATOS}"
)

print(
    f"Intervalo  : {INTERVALO_PAQUETES:.2f} s"
)

print()
print("Transmitiendo paquetes continuamente.")
print("Presioná Ctrl+C para detener.")
print()


# ============================================================
# TRANSMISIÓN CONTINUA
# ============================================================

contador_paquetes = 0

try:
    while True:
        datos_sensor = cargar_datos(origen=ORIGEN_DATOS)

        contador_paquetes += 1
        datos = armar_paquete(contador_paquetes, datos_sensor)

        bits_datos = np.unpackbits(np.frombuffer(datos, dtype=np.uint8)).astype(int)

        # ----------------------------------------------------
        # DSSS
        # ----------------------------------------------------

        chips_dsss = ensanchar(
            bits_datos,
            pn_bipolar
        )

        bits_chips = (
            (chips_dsss + 1) // 2
        ).astype(int)

        bits_chips = "".join(
            str(int(bit))
            for bit in bits_chips
        )

        # ----------------------------------------------------
        # Trama
        # ----------------------------------------------------

        bits_tx = (
            PREAMBULO
            + bits_chips
            + GUARDA
        )

        # ----------------------------------------------------
        # BPSK
        # ----------------------------------------------------

        senal = generar_bpsk(
            bits_tx
        ).astype(
            np.complex64
        )

        # ----------------------------------------------------
        # Mostrar paquete
        # ----------------------------------------------------

        print(f"[TX {contador_paquetes:04d}] {describir_paquete(datos)}")
        print(f"          Bytes: {datos.hex()}")

        # ----------------------------------------------------
        # Transmitir trama
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Finalizar ráfaga
        # ----------------------------------------------------

        sdr.writeStream(
            stream,
            [np.zeros(
                1,
                dtype=np.complex64
            )],
            1,
            flags=SOAPY_SDR_END_BURST
        )

        # ----------------------------------------------------
        # Esperar antes del próximo paquete
        # ----------------------------------------------------

        time.sleep(
            INTERVALO_PAQUETES
        )


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