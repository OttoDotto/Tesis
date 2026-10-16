import os
import sys
from contextlib import contextmanager

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_TX, SOAPY_SDR_CF32

# HackRF: amplificador de RF (0 = apagado, 14.0 = +14 dB). Apagado por defecto:
# satura con facilidad y a corta distancia no hace falta.
HACKRF_AMP_DB = 0.0

# Buffer de recepcion de UHD (frames de ~16 KB). El default (~32 frames) aguanta
# solo ~60 ms a 2 Msps: cualquier pausa del programa mayor a eso = overflow.
# 256 frames ~ 0.5 s. No subir mucho: usbfs_memory_mb suele ser 16 MB por defecto.
UHD_NUM_RECV_FRAMES = 256


@contextmanager
def silenciar_c(activo=True):
    """
    Silencia lo que escriben las librerias C/C++ (UHD, libhackrf) redirigiendo
    los descriptores 1 y 2 a /dev/null. print() de Python tambien se oculta
    mientras dura el bloque.
    """
    if not activo:
        yield
        return
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    guardado_1, guardado_2 = os.dup(1), os.dup(2)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(guardado_1, 1)
        os.dup2(guardado_2, 2)
        for fd in (devnull, guardado_1, guardado_2):
            os.close(fd)


def _ganancia_hackrf(sdr, soapy_modo, canal, ganancia):
    """
    Nombres de elementos segun SoapySDRUtil --probe:
      TX: VGA [0,47] dB (paso 1) | AMP {0,14}
      RX: LNA [0,40] dB (paso 8) | VGA [0,62] dB (paso 2) | AMP {0,14}
    'ganancia' = suma de LNA+VGA (RX) o VGA (TX); el AMP se maneja aparte.
    """
    sdr.setGain(soapy_modo, canal, 'AMP', HACKRF_AMP_DB)
    if soapy_modo == SOAPY_SDR_TX:
        sdr.setGain(soapy_modo, canal, 'VGA', float(min(max(ganancia, 0), 47)))
    else:
        g = max(ganancia, 0)
        lna = min((int(g) // 8) * 8, 40)               # primero LNA (mejor figura de ruido)
        vga = min(((int(g) - lna) // 2) * 2, 62)       # el resto en VGA (pasos de 2)
        sdr.setGain(soapy_modo, canal, 'LNA', float(lna))
        sdr.setGain(soapy_modo, canal, 'VGA', float(vga))


def _texto_ganancia(sdr, soapy_modo, canal, modo):
    """Lee de vuelta lo que el driver realmente aplico."""
    try:
        total = sdr.getGain(soapy_modo, canal)
        detalle = ", ".join(
            f"{n}={sdr.getGain(soapy_modo, canal, n):.1f}"
            for n in sdr.listGains(soapy_modo, canal)
        )
        return f"[SDR] {modo.upper()} ganancia efectiva: total={total:.1f} dB ({detalle})"
    except RuntimeError as e:
        return f"[SDR] No se pudo leer la ganancia efectiva: {e}"


def inicializar_sdr(modo, args, sample_rate, freq_central, ganancia, antena,
                    canal=0, debug=False):
    soapy_modo = SOAPY_SDR_TX if modo.upper() == 'TX' else SOAPY_SDR_RX

    if ('uhd' in args.lower() and soapy_modo == SOAPY_SDR_RX
            and 'num_recv_frames' not in args):
        args = f"{args},num_recv_frames={UHD_NUM_RECV_FRAMES}"

    # En modo limpio, todo el ruido de los drivers queda oculto durante el arranque
    with silenciar_c(activo=not debug):
        sdr = SoapySDR.Device(args)

        sdr.setSampleRate(soapy_modo, canal, sample_rate)
        sdr.setFrequency(soapy_modo, canal, freq_central)
        sdr.setAntenna(soapy_modo, canal, antena)

        if 'hackrf' in args.lower():
            _ganancia_hackrf(sdr, soapy_modo, canal, ganancia)
        else:
            sdr.setGain(soapy_modo, canal, float(ganancia))   # Ettus: ganancia global

        info_ganancia = _texto_ganancia(sdr, soapy_modo, canal, modo)

        stream = sdr.setupStream(soapy_modo, SOAPY_SDR_CF32)
        sdr.activateStream(stream)

    if debug:
        print(info_ganancia)
    return sdr, stream


def cerrar_sdr(sdr, stream, debug=False):
    """Desactiva y cierra el stream de forma segura."""
    if sdr is not None and stream is not None:
        with silenciar_c(activo=not debug):
            sdr.deactivateStream(stream)
            sdr.closeStream(stream)