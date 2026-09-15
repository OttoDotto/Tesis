import os
import time
import numpy as np

from config import (
    DATA_DIR,
    TAPS_PN,
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
    SIMULACION_UN_PAQUETE,
    INTERVALO_SEGUNDOS
)

from datos_utils import cargar_bits_datos, abrir_puerto_serial
from funciones_trama import agregar_preambulo
from funciones_dsss import (
    generar_codigo_pn,
    codificar_hamming,
    ensanchar,
    aplicar_pulse_shaping
)
from sdr_utils import abrir_sdr_tx, transmitir_señal, cerrar_sdr_tx
from paquete import describir_paquete

def preparar_pn():
    return generar_codigo_pn(TAPS_PN, LONGITUD_PN)

def preparar_serial():
    if ORIGEN_DATOS != "s0.2e6erial":
        return None
    conexion = abrir_puerto_serial(PUERTO_SERIAL, BAUDRATE)
    print(f"Puerto serial {PUERTO_SERIAL} abierto.")
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

def generar_trama_tx(bits_datos, pn_bipolar):
    bits_codificados = codificar_hamming(bits_datos)
    chips_datos = ensanchar(bits_codificados, pn_bipolar)
    chips_trama = agregar_preambulo(chips_datos)
    señal_baseband = aplicar_pulse_shaping(chips_trama, sps=SPS, beta=BETA)
    return bits_codificados, chips_datos, chips_trama, señal_baseband

def guardar_paquete_simulacion(bits_originales, bits_codificados, chips_datos, chips_trama, señal_baseband):
    nombre = "paquete_simulacion.npz"
    path = os.path.join(DATA_DIR, nombre)
    tmp_path = os.path.join(DATA_DIR, ".paquete_simulacion.tmp.npz")
    
    np.savez(
        tmp_path,
        bits_originales=bits_originales,
        bits_codificados=bits_codificados,
        chips_datos=chips_datos,
        chips_trama=chips_trama,
        señal_baseband=señal_baseband
    )
    os.replace(tmp_path, path)
    return path

def mostrar_informacion_tx(bits_datos, bits_codificados, chips_datos, chips_trama, señal_baseband):
    bytes_datos = np.packbits(bits_datos).tobytes()
    print("\n" + "=" * 60)
    print("TX — GENERACIÓN DE TRAMA")
    print("=" * 60)
    print(f"Datos originales:        {len(bits_datos)} bits")
    print(f"Hamming:                 {len(bits_codificados)} bits")
    print(f"Datos DSSS:              {len(chips_datos)} chips")
    print(f"Preámbulo:               {len(chips_trama) - len(chips_datos)} chips")
    print(f"Trama total:             {len(chips_trama)} chips")
    print(f"Muestras después RRC:    {len(señal_baseband)}")
    print(f"Duración:                {len(señal_baseband) / SAMPLE_RATE * 1000:.3f} ms")
    try:
        print(f"Datos:                   {describir_paquete(bytes_datos)}")
    except Exception:
        print(f"Datos (Hex):             {bytes_datos.hex()}")
    print("=" * 60)

def ejecutar_tx():
    pn_bipolar = preparar_pn()
    print("TX: Código PN generado y validado.")
    print(f"TX: Paquete de {N_BITS} bits.")

    conexion_serial = preparar_serial()
    sdr, tx_stream = preparar_sdr()

    paquetes_enviados = 0

    try:
        while True:
            bits_datos = cargar_bits_datos(
                origen=ORIGEN_DATOS,
                n_bits=N_BITS,
                conexion=conexion_serial
            )

            bits_codificados, chips_datos, chips_trama, señal_baseband = generar_trama_tx(
                bits_datos,
                pn_bipolar
            )

            paquetes_enviados += 1

            if USAR_SDR:
                print(f"\n[TX #{paquetes_enviados}] Transmitiendo por RF SDR...")
                ok = transmitir_señal(sdr, tx_stream, señal_baseband, canal=CANAL_SDR)
                if ok:
                    print(f"[TX #{paquetes_enviados}] OK")
                else:
                    print(f"[TX #{paquetes_enviados}] ERROR al enviar por SDR")
            else:
                path = guardar_paquete_simulacion(
                    bits_datos, bits_codificados, chips_datos, chips_trama, señal_baseband
                )
                mostrar_informacion_tx(bits_datos, bits_codificados, chips_datos, chips_trama, señal_baseband)
                print(f"\nTX — Simulación guardada en {path}")

            if SIMULACION_UN_PAQUETE:
                print("\nTX — Prueba única finalizada.")
                break

            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print("\nTX detenido por el usuario.")
    finally:
        if sdr is not None:
            cerrar_sdr_tx(sdr, tx_stream)

if __name__ == "__main__":
    ejecutar_tx()