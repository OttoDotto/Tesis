import time
import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32
)

from config import (
    FREQ_CENTRAL,
    SAMPLE_RATE,
    CANAL,
    ANTENA,
    GANANCIA_RX,
    MUESTRAS_POR_BIT,
    PREAMBULO,
    DATOS,
    GUARDA,
    UMBRAL_NIVEL,
    UMBRAL_CORRELACION,
    MUESTRAS_RX
)


# ============================================================
# PREÁMBULO CONOCIDO
# ============================================================

PREAMBULO_SIMBOLOS = np.array(
    [
        1.0 if bit == "1" else -1.0
        for bit in PREAMBULO
    ],
    dtype=np.float32
)


# ============================================================
# BUSCAR PREÁMBULO
# ============================================================

def buscar_preambulo(muestras):

    mejor_correlacion = -1.0
    mejor_inicio = None

    referencia = PREAMBULO_SIMBOLOS.astype(
        np.complex64
    )

    longitud = len(PREAMBULO)

    for offset in range(MUESTRAS_POR_BIT):

        muestras_offset = muestras[offset:]

        cantidad_simbolos = (
            len(muestras_offset)
            // MUESTRAS_POR_BIT
        )

        if cantidad_simbolos < longitud:
            continue

        muestras_offset = muestras_offset[
            :cantidad_simbolos * MUESTRAS_POR_BIT
        ]

        bloques = muestras_offset.reshape(
            cantidad_simbolos,
            MUESTRAS_POR_BIT
        )

        simbolos = np.mean(
            bloques,
            axis=1
        )

        correlaciones = np.correlate(
            simbolos,
            referencia,
            mode="valid"
        )

        energia_rx = np.convolve(
            np.abs(simbolos) ** 2,
            np.ones(
                longitud,
                dtype=np.float32
            ),
            mode="valid"
        )

        energia_ref = np.sum(
            np.abs(referencia) ** 2
        )

        denominador = np.sqrt(
            energia_rx * energia_ref
        )

        correlaciones_normalizadas = (
            np.abs(correlaciones)
            / np.maximum(
                denominador,
                1e-12
            )
        )

        indice = np.argmax(
            correlaciones_normalizadas
        )

        correlacion = (
            correlaciones_normalizadas[indice]
        )

        if correlacion > mejor_correlacion:

            mejor_correlacion = correlacion

            mejor_inicio = (
                offset
                + indice * MUESTRAS_POR_BIT
            )

    if mejor_inicio is None:

        return None, None

    return (
        mejor_correlacion,
        mejor_inicio
    )


# ============================================================
# ESTIMAR OFFSET DE FRECUENCIA
# ============================================================

def estimar_offset_frecuencia(
    simbolos_preambulo
):

    corregidos = (
        simbolos_preambulo
        * PREAMBULO_SIMBOLOS
    )

    fases = np.unwrap(
        np.angle(corregidos)
    )

    indices = np.arange(
        len(fases),
        dtype=np.float64
    )

    pesos = np.maximum(
        np.abs(corregidos) ** 2,
        1e-12
    )

    pendiente, fase_inicial = np.polyfit(
        indices,
        fases,
        1,
        w=pesos
    )

    tasa_simbolos = (
        SAMPLE_RATE
        / MUESTRAS_POR_BIT
    )

    frecuencia_offset = (
        pendiente
        * tasa_simbolos
        / (2.0 * np.pi)
    )

    return (
        pendiente,
        fase_inicial,
        frecuencia_offset
    )


# ============================================================
# ANALIZAR TRAMA
# ============================================================

def analizar_trama(
    muestras,
    inicio
):

    cantidad_bits = (
        len(PREAMBULO)
        + len(DATOS)
        + len(GUARDA)
    )

    cantidad_muestras = (
        cantidad_bits
        * MUESTRAS_POR_BIT
    )

    fin = inicio + cantidad_muestras

    if inicio < 0 or fin > len(muestras):

        return None

    trama = muestras[
        inicio:fin
    ]

    # --------------------------------------------------------
    # CONVERTIR A SÍMBOLOS
    # --------------------------------------------------------

    bloques = trama.reshape(
        cantidad_bits,
        MUESTRAS_POR_BIT
    )

    simbolos = np.mean(
        bloques,
        axis=1
    )

    n_preambulo = len(PREAMBULO)
    n_datos = len(DATOS)

    simbolos_preambulo = (
        simbolos[
            :n_preambulo
        ]
    )

    # --------------------------------------------------------
    # ESTIMAR OFFSET DE FRECUENCIA
    # --------------------------------------------------------

    (
        pendiente_fase,
        fase_inicial,
        frecuencia_offset
    ) = estimar_offset_frecuencia(
        simbolos_preambulo
    )

    # --------------------------------------------------------
    # CORREGIR FASE
    # --------------------------------------------------------

    pendiente_por_muestra = (
        pendiente_fase
        / MUESTRAS_POR_BIT
    )

    indices = np.arange(
        len(trama),
        dtype=np.float64
    )

    fase = (
        fase_inicial
        + pendiente_por_muestra * indices
    )

    trama_corregida = (
        trama
        * np.exp(-1j * fase)
    )

    # --------------------------------------------------------
    # VOLVER A FORMAR SÍMBOLOS
    # --------------------------------------------------------

    bloques_corregidos = (
        trama_corregida.reshape(
            cantidad_bits,
            MUESTRAS_POR_BIT
        )
    )

    simbolos_corregidos = np.mean(
        bloques_corregidos,
        axis=1
    )

    simbolos_preambulo = (
        simbolos_corregidos[
            :n_preambulo
        ]
    )

    simbolos_datos = (
        simbolos_corregidos[
            n_preambulo:
            n_preambulo + n_datos
        ]
    )

    simbolos_guarda = (
        simbolos_corregidos[
            n_preambulo + n_datos:
        ]
    )

    # --------------------------------------------------------
    # DECODIFICAR
    # --------------------------------------------------------

    bits_preambulo = "".join(
        "1" if np.real(simbolo) >= 0 else "0"
        for simbolo in simbolos_preambulo
    )

    bits_datos = "".join(
        "1" if np.real(simbolo) >= 0 else "0"
        for simbolo in simbolos_datos
    )

    bits_guarda = "".join(
        "1" if np.real(simbolo) >= 0 else "0"
        for simbolo in simbolos_guarda
    )

    # --------------------------------------------------------
    # ERRORES
    # --------------------------------------------------------

    errores_preambulo = sum(
        a != b
        for a, b in zip(
            bits_preambulo,
            PREAMBULO
        )
    )

    errores_datos = sum(
        a != b
        for a, b in zip(
            bits_datos,
            DATOS
        )
    )

    errores_guarda = sum(
        a != b
        for a, b in zip(
            bits_guarda,
            GUARDA
        )
    )

    return {
        "bits_preambulo": bits_preambulo,
        "bits_datos": bits_datos,
        "bits_guarda": bits_guarda,

        "errores_preambulo": errores_preambulo,
        "errores_datos": errores_datos,
        "errores_guarda": errores_guarda,

        "pendiente_fase": pendiente_fase,
        "fase_inicial": fase_inicial,
        "frecuencia_offset": frecuencia_offset,

        "simbolos_guarda": simbolos_guarda
    }


# ============================================================
# CONFIGURAR SDR
# ============================================================

sdr = SoapySDR.Device(
    "driver=uhd"
)

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

stream = sdr.setupStream(
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32
)

sdr.activateStream(stream)


# ============================================================
# INFORMACIÓN
# ============================================================

print()
print("============================================")
print("RECEPTOR BPSK")
print("============================================")

print(
    f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz"
)

print(
    f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps"
)

print(
    f"Ganancia   : {GANANCIA_RX}"
)

print(
    f"Antena     : {ANTENA}"
)

print()

print(
    f"Muestras/símbolo: {MUESTRAS_POR_BIT}"
)

print(
    f"Tasa de símbolos: "
    f"{SAMPLE_RATE / MUESTRAS_POR_BIT / 1e3:.3f} ksym/s"
)

print()

print(
    f"Preámbulo: {PREAMBULO}"
)

print(
    f"Datos    : {DATOS}"
)

print(
    f"Guarda   : {len(GUARDA)} bits"
)

print()


# ============================================================
# RECEPCIÓN
# ============================================================

buffer_rx = np.zeros(
    MUESTRAS_RX,
    dtype=np.complex64
)

try:

    while True:

        resultado = sdr.readStream(
            stream,
            [buffer_rx],
            MUESTRAS_RX
        )

        if resultado.ret < 0:

            print(
                f"Error RX: {resultado.ret}"
            )

            continue

        cantidad = resultado.ret

        if cantidad == 0:
            continue

        muestras = buffer_rx[
            :cantidad
        ].copy()

        # ----------------------------------------------------
        # DETECTAR SEÑAL
        # ----------------------------------------------------

        nivel_maximo = np.max(
            np.abs(muestras)
        )

        if nivel_maximo < UMBRAL_NIVEL:

            continue

        print()
        print(
            "Señal detectada."
        )

        # ----------------------------------------------------
        # BUSCAR PREÁMBULO
        # ----------------------------------------------------

        (
            correlacion,
            inicio
        ) = buscar_preambulo(
            muestras
        )

        if correlacion is None:

            print(
                "No se encontró preámbulo."
            )

            continue

        print(
            f"Correlación: {correlacion:.3f}"
        )

        print(
            f"Inicio: {inicio}"
        )

        if correlacion < UMBRAL_CORRELACION:

            print(
                "Correlación inferior "
                "al umbral."
            )

            continue

        # ----------------------------------------------------
        # ANALIZAR TRAMA
        # ----------------------------------------------------

        resultado_trama = analizar_trama(
            muestras,
            inicio
        )

        if resultado_trama is None:

            print(
                "No hay suficientes muestras "
                "para analizar la trama."
            )

            continue

        # ----------------------------------------------------
        # RESULTADOS
        # ----------------------------------------------------

        print()
        print(
            "============================================"
        )
        print(
            "RESULTADO"
        )
        print(
            "============================================"
        )

        print(
            f"Preámbulo recibido: "
            f"{resultado_trama['bits_preambulo']}"
        )

        print(
            f"Errores preámbulo: "
            f"{resultado_trama['errores_preambulo']}"
        )

        print()

        print(
            f"Datos recibidos: "
            f"{resultado_trama['bits_datos']}"
        )

        print(
            f"Datos esperados : "
            f"{DATOS}"
        )

        print(
            f"Errores datos: "
            f"{resultado_trama['errores_datos']}"
        )

        print()

        print(
            f"Errores guarda: "
            f"{resultado_trama['errores_guarda']}"
        )

        print(
            f"Bits de guarda recibidos: "
            f"{len(resultado_trama['bits_guarda'])}"
        )

        print()

        print(
            f"Fase inicial: "
            f"{np.degrees(resultado_trama['fase_inicial']):+.1f} grados"
        )

        print(
            f"Variación de fase: "
            f"{np.degrees(resultado_trama['pendiente_fase']):+.3f} "
            f"grados/símbolo"
        )

        print(
            f"Offset de frecuencia: "
            f"{resultado_trama['frecuencia_offset']:+.1f} Hz"
        )

        print()

        if (
            resultado_trama["errores_preambulo"] == 0
            and resultado_trama["errores_datos"] == 0
        ):

            print(
                "PRUEBA SUPERADA: "
                "PREÁMBULO Y DATOS CORRECTOS."
            )

        else:

            print(
                "PRUEBA FALLIDA."
            )

        print()

        time.sleep(0.5)


except KeyboardInterrupt:

    print()
    print("RX detenido.")


finally:

    sdr.deactivateStream(stream)
    sdr.closeStream(stream)