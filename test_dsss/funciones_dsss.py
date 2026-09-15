"""
Funciones núcleo del sistema DSSS-BPSK: todo lo que necesitan
tanto el transmisor como el receptor para operar sobre la señal.
"""

import numpy as np


# --- Código PN ---

def generar_secuencia_m(taps, longitud):
    """
    Genera una secuencia m mediante un LFSR.

    Para taps=[6, 1]:
        x^6 + x + 1

    genera una secuencia máxima de período 2^6 - 1 = 63.
    """

    n = max(taps)

    # Estado inicial distinto de cero
    registro = [1] * n

    secuencia = []

    for _ in range(longitud):

        # Salida del registro
        salida = registro[-1]
        secuencia.append(salida)

        # Realimentación
        nuevo_bit = 0

        for t in taps:
            nuevo_bit ^= registro[n - t]

        # Desplazamiento
        registro = [nuevo_bit] + registro[:-1]

    return np.array(secuencia)


def autocorrelacion_circular(seq):
    N = len(seq)
    return np.array([np.sum(seq * np.roll(seq, -k)) for k in range(N)])


def generar_codigo_pn(taps, longitud):
    """Genera el código PN bipolar y valida su autocorrelación. Usan TX y RX por igual."""
    pn_code = generar_secuencia_m(taps, longitud)
    pn_bipolar = 2 * pn_code - 1
    autocorr = autocorrelacion_circular(pn_bipolar)
    assert autocorr[0] == longitud and np.all(autocorr[1:] == -1), \
        "Código PN inválido: la autocorrelación no cumple la propiedad esperada"
    return pn_bipolar


# --- Ensanchado / Despread (TX y RX) ---

def ensanchar(bits_datos, pn_bipolar):
    bits_bipolar = 2*bits_datos - 1
    bits_expandido = np.repeat(bits_bipolar, len(pn_bipolar))
    pn_repetido = np.tile(pn_bipolar, len(bits_datos))
    return bits_expandido * pn_repetido


def despreader(señal, pn_bipolar):
    n_chips = len(pn_bipolar)
    n_bits = len(señal) // n_chips
    bits_recuperados = np.zeros(n_bits, dtype=int)
    correlaciones = np.zeros(n_bits)
    for i in range(n_bits):
        bloque = señal[i*n_chips : (i+1)*n_chips]
        correlacion = np.real(np.sum(bloque * pn_bipolar))
        correlaciones[i] = correlacion
        bits_recuperados[i] = 1 if correlacion > 0 else 0
    return bits_recuperados, correlaciones


def refinar_fase(simbolos_datos, pn_bipolar):
    """
    Estima y corrige la pendiente de fase residual usando los
    propios datos DSSS (mucho más largos que el preámbulo).

    Eleva al cuadrado las correlaciones complejas por bit para
    eliminar la modulación BPSK (±1 -> +1) y deja solo el giro
    de fase residual. Se corrige SOLO la pendiente: la fase
    absoluta ya viene bien del preámbulo, y el cuadrado tiene
    ambigüedad de 180 grados.
    """

    n_chips = len(pn_bipolar)

    n_bits = len(simbolos_datos) // n_chips

    bloques = simbolos_datos[
        :n_bits * n_chips
    ].reshape(n_bits, n_chips)

    # Correlación COMPLEJA por bit (no solo la parte real)
    correlaciones = bloques @ pn_bipolar

    fase_doble = np.unwrap(
        np.angle(correlaciones ** 2)
    )

    indices_bits = np.arange(
        n_bits,
        dtype=np.float64
    )

    pesos = np.maximum(
        np.abs(correlaciones) ** 2,
        1e-12
    )

    pendiente_doble, _ = np.polyfit(
        indices_bits,
        fase_doble,
        1,
        w=pesos
    )

    pendiente_bit = pendiente_doble / 2.0
    pendiente_chip = pendiente_bit / n_chips

    indices_chips = np.arange(
        len(simbolos_datos),
        dtype=np.float64
    )

    corregidos = simbolos_datos * np.exp(
        -1j * pendiente_chip * indices_chips
    )

    return corregidos, pendiente_chip


# --- Modulación / Demodulación (pulse shaping, TX y RX) ---

def filtro_rrc(beta, sps, n_taps):
    t = (np.arange(n_taps) - (n_taps-1)/2) / sps
    h = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti == 0:
            h[i] = 1.0 - beta + 4*beta/np.pi
        elif beta != 0 and abs(ti) == 1/(4*beta):
            h[i] = (beta/np.sqrt(2)) * (
                ((1+2/np.pi)*np.sin(np.pi/(4*beta))) +
                ((1-2/np.pi)*np.cos(np.pi/(4*beta)))
            )
        else:
            h[i] = (
                np.sin(np.pi*ti*(1-beta)) +
                4*beta*ti*np.cos(np.pi*ti*(1+beta))
            ) / (np.pi*ti*(1-(4*beta*ti)**2))
    return h / np.sqrt(np.sum(h**2))


def aplicar_pulse_shaping(chips, sps=8, beta=0.35, n_taps=65):
    """TX: de chips discretos ±1 a forma de onda continua."""
    chips_upsampled = np.zeros(len(chips) * sps)
    chips_upsampled[::sps] = chips
    h = filtro_rrc(beta, sps, n_taps)
    return np.convolve(chips_upsampled, h, mode='same')


def filtro_adaptado(
    señal_recibida,
    sps,
    beta=0.35,
    n_taps=65,
    offset=0
):
    """
    RX: filtro adaptado + muestreo de símbolos.

    offset permite seleccionar el instante de muestreo
    dentro de los SPS posibles.
    """

    h = filtro_rrc(
        beta,
        sps,
        n_taps
    )

    filtrada = np.convolve(
        señal_recibida,
        h,
        mode='same'
    )

    return filtrada[offset::sps]


# --- Corrección de errores (TX y RX) ---

def codificar_hamming(bits):
    assert len(bits) % 4 == 0, "La cantidad de bits debe ser múltiplo de 4 para Hamming(7,4)"
    bloques = bits.reshape(-1, 4)
    codewords = []
    for d1, d2, d3, d4 in bloques:
        p1 = d1 ^ d2 ^ d4
        p2 = d1 ^ d3 ^ d4
        p3 = d2 ^ d3 ^ d4
        codewords.append([p1, p2, d1, p3, d2, d3, d4])
    return np.array(codewords).flatten()


def decodificar_hamming(bits_codificados):
    assert len(bits_codificados) % 7 == 0
    bloques = bits_codificados.reshape(-1, 7).copy()
    bits_recuperados = []
    errores_corregidos = 0
    for bloque in bloques:
        p1, p2, d1, p3, d2, d3, d4 = bloque
        s1 = p1 ^ d1 ^ d2 ^ d4
        s2 = p2 ^ d1 ^ d3 ^ d4
        s3 = p3 ^ d2 ^ d3 ^ d4
        syndrome = s1 + 2*s2 + 4*s3
        if syndrome != 0:
            bloque[syndrome - 1] ^= 1
            errores_corregidos += 1
            p1, p2, d1, p3, d2, d3, d4 = bloque
        bits_recuperados.extend([d1, d2, d3, d4])
    return np.array(bits_recuperados), errores_corregidos


# --- Canal (temporal, hasta tener hardware real) ---
def agregar_ruido(señal, snr_db):
    """
    Agrega ruido AWGN complejo a una señal IQ.
    """

    potencia_señal = np.mean(
        np.abs(señal) ** 2
    )

    snr_lineal = 10 ** (
        snr_db / 10
    )

    potencia_ruido = (
        potencia_señal / snr_lineal
    )

    sigma = np.sqrt(
        potencia_ruido / 2
    )

    ruido = sigma * (
        np.random.randn(len(señal))
        +
        1j * np.random.randn(len(señal))
    )

    return señal + ruido