import os
import time
import numpy as np

from config import (
    DATA_DIR,
    TAPS_PN,
    POLINOMIOS_PRIMITIVOS,
    LONGITUD_PN,
    N_BITS,
    ORIGEN_DATOS,
    SPS,
    BETA,
    USAR_SDR,
    PUERTO_SERIAL,
    BAUDRATE,
    SAMPLE_RATE,
    SDR_ARGS,
    CANAL_SDR,
    FREQ_CENTRAL,
    GANANCIA_TX,
    ANTENA_TX,
    SIMULACION_UN_PAQUETE
)

from datos_utils import (
    cargar_bits_datos,
    abrir_puerto_serial
)

from funciones_trama import (
    agregar_preambulo
)

from funciones_dsss import (
    generar_codigo_pn,
    codificar_hamming,
    ensanchar,
    aplicar_pulse_shaping
)

from sdr_utils import (
    abrir_sdr_tx,
    transmitir_señal,
    cerrar_sdr_tx
)

from paquete import describir_paquete


# ============================================================
# PREPARACIÓN DEL TRANSMISOR
# ============================================================

def preparar_pn():

    return generar_codigo_pn(
        TAPS_PN,
        LONGITUD_PN
    )


def preparar_serial():

    if ORIGEN_DATOS != "serial":

        return None

    conexion = abrir_puerto_serial(
        PUERTO_SERIAL,
        BAUDRATE
    )

    print(
        f"Puerto serial {PUERTO_SERIAL} abierto."
    )

    return conexion


def preparar_sdr():

    if not USAR_SDR:

        return None, None

    return abrir_sdr_tx(
        args=SDR_ARGS,
        canal=CANAL_SDR,
        freq_hz=FREQ_CENTRAL,
        sample_rate=SAMPLE_RATE,
        ganancia_db=GANANCIA_TX,
        antena=ANTENA_TX,
    )


# ============================================================
# GENERACIÓN DE LA TRAMA
# ============================================================

def generar_trama_tx(
    bits_datos,
    pn_bipolar
):

    # ========================================================
    # 1. HAMMING
    # ========================================================

    bits_codificados = codificar_hamming(
        bits_datos
    )

    # ========================================================
    # 2. DSSS
    # ========================================================

    chips_datos = ensanchar(
        bits_codificados,
        pn_bipolar
    )

    # ========================================================
    # 3. PREÁMBULO
    # ========================================================

    chips_trama = agregar_preambulo(
        chips_datos
    )

    # ========================================================
    # 4. PULSE SHAPING
    # ========================================================

    señal_baseband = aplicar_pulse_shaping(
        chips_trama,
        sps=SPS,
        beta=BETA
    )

    return (
        bits_codificados,
        chips_datos,
        chips_trama,
        señal_baseband
    )


# ============================================================
# GUARDAR SIMULACIÓN
# ============================================================

def guardar_paquete_simulacion(
    bits_originales,
    bits_codificados,
    chips_datos,
    chips_trama,
    señal_baseband
):

    nombre = "paquete_simulacion.npz"

    path = os.path.join(
        DATA_DIR,
        nombre
    )

    tmp_path = os.path.join(
        DATA_DIR,
        ".paquete_simulacion.tmp.npz"
    )

    np.savez(
        tmp_path,

        bits_originales=bits_originales,

        bits_codificados=bits_codificados,

        chips_datos=chips_datos,

        chips_trama=chips_trama,

        señal_baseband=señal_baseband
    )

    os.replace(
        tmp_path,
        path
    )

    return path


# ============================================================
# INFORMACIÓN
# ============================================================

def mostrar_informacion_tx(
    bits_datos,
    bits_codificados,
    chips_datos,
    chips_trama,
    señal_baseband
):

    bytes_datos = np.packbits(
        bits_datos
    ).tobytes()

    print()
    print("=" * 60)
    print("TX — GENERACIÓN DE TRAMA")
    print("=" * 60)

    print(
        f"Datos originales:        "
        f"{len(bits_datos)} bits"
    )

    print(
        f"Hamming:                 "
        f"{len(bits_codificados)} bits"
    )

    print(
        f"Datos DSSS:              "
        f"{len(chips_datos)} chips"
    )

    print(
        f"Preámbulo:               "
        f"{len(chips_trama) - len(chips_datos)} chips"
    )

    print(
        f"Trama total:             "
        f"{len(chips_trama)} chips"
    )

    print(
        f"Muestras después RRC:    "
        f"{len(señal_baseband)}"
    )

    print(
        f"Duración:                "
        f"{len(señal_baseband) / SAMPLE_RATE * 1000:.3f} ms"
    )

    print(
        f"Datos:                   "
        f"{describir_paquete(bytes_datos)}"
    )

    print("=" * 60)


# ============================================================
# ORQUESTADOR TX
# ============================================================

def ejecutar_tx():

    # ========================================================
    # PREPARACIÓN
    # ========================================================

    pn_bipolar = preparar_pn()

    print(
        f"TX: Código PN generado y validado."
    )

    print(
        f"TX: Paquete de {N_BITS} bits."
    )

    conexion_serial = preparar_serial()

    sdr, tx_stream = preparar_sdr()

    try:

        # ====================================================
        # GENERAR UN PAQUETE
        # ====================================================

        bits_datos = cargar_bits_datos(
            origen=ORIGEN_DATOS,
            n_bits=N_BITS,
            conexion=conexion_serial
        )

        # ====================================================
        # GENERAR TRAMA
        # ====================================================

        (
            bits_codificados,
            chips_datos,
            chips_trama,
            señal_baseband
        ) = generar_trama_tx(
            bits_datos,
            pn_bipolar
        )

        # ====================================================
        # INFORMACIÓN
        # ====================================================

        mostrar_informacion_tx(
            bits_datos,
            bits_codificados,
            chips_datos,
            chips_trama,
            señal_baseband
        )

        # ====================================================
        # TRANSMISIÓN SDR
        # ====================================================

        if USAR_SDR:

            print()
            print(
                "TX SDR — transmitiendo..."
            )

            ok = transmitir_señal(
                sdr,
                tx_stream,
                señal_baseband,
                canal=CANAL_SDR
            )

            if ok:

                print(
                    "TX SDR — transmisión OK."
                )

            else:

                print(
                    "TX SDR — error."
                )

        # ====================================================
        # SIMULACIÓN
        # ====================================================

        else:

            path = guardar_paquete_simulacion(
                bits_originales=bits_datos,
                bits_codificados=bits_codificados,
                chips_datos=chips_datos,
                chips_trama=chips_trama,
                señal_baseband=señal_baseband
            )

            print()
            print(
                "TX — simulación guardada."
            )

            print(
                f"Archivo: {path}"
            )

        # ====================================================
        # ESPERAR
        # ====================================================

        if SIMULACION_UN_PAQUETE:

            print()
            print(
                "TX — prueba finalizada."
            )

        else:

            while True:

                time.sleep(
                    1
                )

    except KeyboardInterrupt:

        print(
            "\nTX detenido por el usuario."
        )

    finally:

        if sdr is not None:

            cerrar_sdr_tx(
                sdr,
                tx_stream
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    ejecutar_tx()