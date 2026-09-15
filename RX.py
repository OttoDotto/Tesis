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
    CANAL_SDR,
    ANTENA_RX,
    GANANCIA_RX,
    MUESTRAS_POR_BIT,
    PREAMBULO,
    GUARDA,
    UMBRAL_NIVEL,
    UMBRAL_CORRELACION,
    MUESTRAS_RX,
    LONGITUD_PN,
    TAPS_PN
)

from paquete import (
    TAMAÑO_PAQUETE_BYTES,
    describir_paquete,
    generar_paquete_ejemplo
)

from funciones_dsss import (
    generar_codigo_pn,
    despreader,
    refinar_fase
)


# ============================================================
# CONSTANTES
# ============================================================

CANTIDAD_BITS_DATOS = (
    TAMAÑO_PAQUETE_BYTES * 8
)

CANTIDAD_CHIPS_DATOS = (
    CANTIDAD_BITS_DATOS
    * LONGITUD_PN
)


PREAMBULO_SIMBOLOS = np.array(
    [
        1.0 if bit == "1" else -1.0
        for bit in PREAMBULO
    ],
    dtype=np.float32
)


# ============================================================
# CÓDIGO PN
# ============================================================

pn_bipolar = generar_codigo_pn(
    TAPS_PN,
    LONGITUD_PN
)


# ============================================================
# PAQUETE ESPERADO
# ============================================================

# Durante esta prueba usamos ORIGEN_DATOS = "ejemplo"
# para tener un paquete conocido.

datos_esperados = generar_paquete_ejemplo(
    aleatorio=False
)

bits_esperados = np.unpackbits(
    np.frombuffer(
        datos_esperados,
        dtype=np.uint8
    )
).astype(int)


# ============================================================
# BÚSQUEDA DEL PREÁMBULO
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
# ESTIMACIÓN DE OFFSET DE FRECUENCIA
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
# ANÁLISIS DE TRAMA
# ============================================================

def analizar_trama(
    muestras,
    inicio
):

    cantidad_simbolos = (
        len(PREAMBULO)
        + CANTIDAD_CHIPS_DATOS
        + len(GUARDA)
    )

    cantidad_muestras = (
        cantidad_simbolos
        * MUESTRAS_POR_BIT
    )

    fin = inicio + cantidad_muestras

    if inicio < 0 or fin > len(muestras):

        return None

    # --------------------------------------------------------
    # Extraer trama
    # --------------------------------------------------------

    trama = muestras[
        inicio:fin
    ]

    # --------------------------------------------------------
    # Convertir muestras a símbolos/chips
    # --------------------------------------------------------

    bloques = trama.reshape(
        cantidad_simbolos,
        MUESTRAS_POR_BIT
    )

    simbolos = np.mean(
        bloques,
        axis=1
    )

    n_preambulo = len(PREAMBULO)

    simbolos_preambulo = (
        simbolos[
            :n_preambulo
        ]
    )

    # --------------------------------------------------------
    # Estimar fase y offset de frecuencia
    # usando solamente el preámbulo
    # --------------------------------------------------------

    (
        pendiente_fase,
        fase_inicial,
        frecuencia_offset
    ) = estimar_offset_frecuencia(
        simbolos_preambulo
    )

    # --------------------------------------------------------
    # CORRECCIÓN DE FASE
    # --------------------------------------------------------

    indices_simbolos = np.arange(
        cantidad_simbolos,
        dtype=np.float64
    )

    fase_simbolos = (
        fase_inicial
        + pendiente_fase * indices_simbolos
    )

    simbolos_corregidos = (
        simbolos
        * np.exp(-1j * fase_simbolos)
    )

    # --------------------------------------------------------
    # Separar las tres partes
    # --------------------------------------------------------

    simbolos_preambulo = (
        simbolos_corregidos[
            :n_preambulo
        ]
    )

    simbolos_datos = (
        simbolos_corregidos[
            n_preambulo:
            n_preambulo + CANTIDAD_CHIPS_DATOS
        ]
    )

    simbolos_guarda = (
        simbolos_corregidos[
            n_preambulo + CANTIDAD_CHIPS_DATOS:
        ]
    )

    # --------------------------------------------------------
    # Demodular preámbulo
    # --------------------------------------------------------

    bits_preambulo = "".join(
        "1" if np.real(simbolo) >= 0 else "0"
        for simbolo in simbolos_preambulo
    )

    errores_preambulo = sum(
        a != b
        for a, b in zip(
            bits_preambulo,
            PREAMBULO
        )
    )

    # --------------------------------------------------------
    # REFINAMIENTO DE FASE SOBRE LOS DATOS
    #
    # El preámbulo solo dura 32 símbolos (0.26 ms) y los datos
    # duran 5040 chips (40 ms). Extrapolar la pendiente del
    # preámbulo deja un residuo de decenas de Hz que rota la
    # constelación e invierte los bits a mitad del paquete.
    # --------------------------------------------------------

    (
        simbolos_datos,
        pendiente_residual
    ) = refinar_fase(
        simbolos_datos,
        pn_bipolar
    )

    # --------------------------------------------------------
    # DESPREADING
    # --------------------------------------------------------

    bits_datos, correlaciones_dsss = despreader(
        simbolos_datos,
        pn_bipolar
    )

    # --------------------------------------------------------
    # Guarda
    # --------------------------------------------------------

    bits_guarda = "".join(
        "1" if np.real(simbolo) >= 0 else "0"
        for simbolo in simbolos_guarda
    )

    return {
        "bits_preambulo":
            bits_preambulo,

        "errores_preambulo":
            errores_preambulo,

        "chips_recibidos":
            len(simbolos_datos),

        "bits_datos":
            bits_datos,

        "correlaciones_dsss":
            correlaciones_dsss,

        "bits_guarda":
            bits_guarda,

        "pendiente_residual":
            pendiente_residual,

        "pendiente_fase":
            pendiente_fase,

        "fase_inicial":
            fase_inicial,

        "frecuencia_offset":
            frecuencia_offset
    }

# ============================================================
# SDR
# ============================================================

sdr = SoapySDR.Device(
    "driver=uhd"
)

sdr.setSampleRate(
    SOAPY_SDR_RX,
    CANAL_SDR,
    SAMPLE_RATE
)

sdr.setFrequency(
    SOAPY_SDR_RX,
    CANAL_SDR,
    FREQ_CENTRAL
)

sdr.setGain(
    SOAPY_SDR_RX,
    CANAL_SDR,
    GANANCIA_RX
)

sdr.setAntenna(
    SOAPY_SDR_RX,
    CANAL_SDR,
    ANTENA_RX
)

stream = sdr.setupStream(
    SOAPY_SDR_RX,
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
print("RECEPTOR DSSS-BPSK - DATOS REALES")
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
    f"Ganancia   : {GANANCIA_RX}"
)

print(
    f"Antena     : {ANTENA_RX}"
)

print()

print(
    f"Preámbulo  : {len(PREAMBULO)} bits"
)

print(
    f"Datos      : {CANTIDAD_BITS_DATOS} bits"
)

print(
    f"PN         : {LONGITUD_PN} chips/bit"
)

print(
    f"Chips datos: {CANTIDAD_CHIPS_DATOS}"
)

print(
    f"Guarda     : {len(GUARDA)} bits"
)

print()

print("PAQUETE ESPERADO")
print("--------------------------------------------")

print(
    describir_paquete(
        datos_esperados
    )
)

print(
    f"Bytes esperados: "
    f"{datos_esperados.hex()}"
)

print()

buffer_rx = np.zeros(
    MUESTRAS_RX,
    dtype=np.complex64
)


# ============================================================
# RECEPCIÓN
# ============================================================

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

        nivel_maximo = np.max(
            np.abs(muestras)
        )

        if nivel_maximo < UMBRAL_NIVEL:
            continue

        print()
        print("Señal detectada.")

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


        # ====================================================
        # RECUPERAR PAQUETE
        # ====================================================

        bits_datos = resultado_trama[
            "bits_datos"
        ]

        errores_datos = np.sum(
            bits_datos != bits_esperados
        )

        datos_rx = np.packbits(
            bits_datos
        ).tobytes()


        # ====================================================
        # RESULTADO
        # ====================================================

        print()
        print("============================================")
        print("RESULTADO")
        print("============================================")

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
            f"Chips DSSS recibidos: "
            f"{resultado_trama['chips_recibidos']}"
        )

        print()

        print(
            "Bits de datos recuperados:"
        )

        print(
            "".join(
                str(int(bit))
                for bit in bits_datos
            )
        )

        print()

        print(
            f"Errores de bits DSSS: "
            f"{errores_datos}/80"
        )

        print()

        print(
            f"Bytes esperados: "
            f"{datos_esperados.hex()}"
        )

        print(
            f"Bytes recibidos: "
            f"{datos_rx.hex()}"
        )

        print()

        try:

            print(
                "Paquete interpretado:"
            )

            print(
                describir_paquete(
                    datos_rx
                )
            )

        except ValueError as e:

            print(
                f"Error interpretando paquete: {e}"
            )

        print()

        print(
            f"Fase inicial: "
            f"{np.degrees(resultado_trama['fase_inicial']):+.1f} grados"
        )

        print(
            f"Variación de fase: "
            f"{np.degrees(resultado_trama['pendiente_fase']):+.3f} "
            f"grados/chip"
        )

        print(
            f"Offset de frecuencia: "
            f"{resultado_trama['frecuencia_offset']:+.1f} Hz"
        )

        pendiente_residual = resultado_trama[
            "pendiente_residual"
        ]

        residual_hz = (
            pendiente_residual
            * (SAMPLE_RATE / MUESTRAS_POR_BIT)
            / (2.0 * np.pi)
        )

        print(
            f"Residuo corregido: "
            f"{np.degrees(pendiente_residual):+.4f} grados/chip "
            f"({residual_hz:+.1f} Hz)"
        )

        print()

        # ----------------------------------------------------
        # Correlaciones DSSS
        # ----------------------------------------------------

        correlaciones = (
            resultado_trama[
                "correlaciones_dsss"
            ]
        )

        print(
            f"Correlación DSSS mínima: "
            f"{np.min(np.abs(correlaciones)):.2f}"
        )

        print(
            f"Correlación DSSS máxima: "
            f"{np.max(np.abs(correlaciones)):.2f}"
        )

        print()

        print("Correlaciones DSSS:")
        print("--------------------------------------------")

        print(
            " ".join(
                f"{c:+.2f}"
                for c in correlaciones
            )
        )

        print()

        # ----------------------------------------------------
        # Resultado de la prueba
        # ----------------------------------------------------

        if (
            resultado_trama[
                "errores_preambulo"
            ] == 0
            and errores_datos == 0
        ):

            print(
                "PRUEBA SUPERADA:"
            )

            print(
                "Preámbulo y datos DSSS "
                "recibidos correctamente."
            )

        else:

            print(
                "PRUEBA NO SUPERADA."
            )

            print(
                "El preámbulo fue detectado, "
                "pero los datos DSSS "
                "no coinciden."
            )

        print()


except KeyboardInterrupt:

    print()
    print("RX detenido.")


finally:

    sdr.deactivateStream(
        stream
    )

    sdr.closeStream(
        stream
    )