#!/usr/bin/env python3
"""
Pantalla de telemetria (curses) para el receptor DSSS.

Uso normal (lo lanza main.py):
    python3 main.py -m rx -d hackrf -a TX/RX -g 60

Vista previa con datos de ejemplo (sin SDR):
    python3 pantalla.py
"""
import curses
import locale
import os
import threading
import time
from contextlib import contextmanager

from paquete import interpretar_paquete


# ============================================================
# PARAMETROS DE LA PANTALLA
# ============================================================
REFRESCO_MS = 200        # cada cuanto se redibuja aunque no llegue nada
TIMEOUT_ENLACE_S = 3.0   # sin tramas validas por este tiempo -> ENLACE PERDIDO


# ============================================================
# ESTADO COMPARTIDO RX -> PANTALLA
# ============================================================
class EstadoRX:
    """
    Puente entre el hilo del receptor (que escribe) y la pantalla (que lee).
    RX.py solo llama a sdr_listo() y trama(); nunca toca curses.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.listo = threading.Event()   # el SDR ya esta transmitiendo muestras
        self.fin = threading.Event()     # el hilo del receptor termino
        self.excepcion = None            # error fatal del receptor (si lo hubo)
        self._stats = None
        self._fijo = False               # solo para la vista previa
        self._d = {
            "datos": None,               # ultima telemetria valida (dict)
            "t_ultima": None,            # time.monotonic() de esa trama
            "ts": None,                  # timestamp legible de esa trama
            "validos": 0,
            "descartados": 0,
            "corr": None,
            "cfo": None,
            "calidad": None,
            "pico": None,
        }

    # ---- lo llama RX.py -------------------------------------------------
    def sdr_listo(self, stats=None):
        self._stats = stats
        self.listo.set()

    def trama(self, ts, payload, corr, res, pico, validos, descartados):
        """payload=None -> trama descartada (correlacion baja o CRC invalido)."""
        with self._lock:
            d = self._d
            d["validos"], d["descartados"] = validos, descartados
            d["corr"], d["pico"] = corr, pico
            if res is not None:
                d["cfo"] = res["frecuencia_offset"]
                d["calidad"] = res["calidad"]
            if payload is not None:
                lat, lon, vel, rumbo, bateria = interpretar_paquete(payload)
                d["datos"] = {"lat": lat, "lon": lon, "vel": vel,
                              "rumbo": rumbo, "bateria": int(bateria)}
                d["t_ultima"] = time.monotonic()
                d["ts"] = ts

    # ---- lo lee la pantalla ---------------------------------------------
    def instantanea(self):
        with self._lock:
            d = dict(self._d)
        d["overflows"] = self._stats["overflows"] if self._stats else 0
        if d["t_ultima"] is None:
            d["edad"] = None
        else:
            d["edad"] = 0.0 if self._fijo else time.monotonic() - d["t_ultima"]
        return d

    @classmethod
    def demo(cls):
        """Estado con datos de ejemplo, para probar el dibujo sin SDR."""
        e = cls()
        e._fijo = True
        e._d.update(
            datos={"lat": -34.6037, "lon": -58.3816, "vel": 12.5,
                   "rumbo": 90.0, "bateria": 85},
            t_ultima=time.monotonic(), ts="demo",
            validos=1, descartados=0, corr=0.93, cfo=1234.5, calidad=0.8, pico=0.4)
        e.listo.set()
        return e


# ============================================================
# UTILIDADES DE DIBUJO
# ============================================================
def put(win, y, x, texto, attr=0):
    """Escribe sin provocar errores si el texto no entra."""
    try:
        win.addstr(y, x, texto, attr)
    except curses.error:
        pass


def campo(win, y, x, etiqueta, valor, attr=0):
    put(win, y, x, etiqueta)
    put(win, y, x + len(etiqueta), valor, attr)


def confirmar_salida(stdscr, c_alerta):
    """Confirma la salida mediante S o cancela con N/Esc."""
    msg = "  ¿DESEA SALIR DE LA INTERFAZ? [S/N]  "
    attr = c_alerta | curses.A_REVERSE | curses.A_BOLD

    stdscr.timeout(-1)

    try:
        while True:
            alto, ancho = stdscr.getmaxyx()
            y = alto // 2
            x = max(0, (ancho - len(msg)) // 2)

            put(stdscr, y - 1, x, " " * len(msg), attr)
            put(stdscr, y, x, msg, attr)
            put(stdscr, y + 1, x, " " * len(msg), attr)

            stdscr.refresh()
            tecla = stdscr.getch()

            if tecla in (ord("s"), ord("S")):
                return True

            if tecla in (ord("n"), ord("N"), 27):
                return False
    finally:
        # volver al modo con refresco periodico (si no, la pantalla se congela)
        stdscr.timeout(REFRESCO_MS)


# ============================================================
# INTERFAZ
# ============================================================
def interfaz(stdscr, estado):
    curses.curs_set(0)
    stdscr.timeout(REFRESCO_MS)

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

    c_ok = curses.color_pair(1)
    c_borde = curses.color_pair(2)
    c_alerta = curses.color_pair(3)
    c_info = curses.color_pair(4)

    while True:
        # el receptor termino (error o parada): salir de la pantalla
        if estado.fin.is_set():
            break

        s = estado.instantanea()
        datos = s["datos"]
        edad = s["edad"]

        stdscr.erase()
        alto, ancho = stdscr.getmaxyx()

        if alto < 18 or ancho < 65:
            put(
                stdscr, 0, 0,
                "AMPLIAR TERMINAL (Minimo: 65x18)"[:max(0, ancho - 1)],
                c_info
            )
            stdscr.refresh()
            tecla = stdscr.getch()

            if tecla in (ord("q"), ord("Q")):
                if confirmar_salida(stdscr, c_alerta):
                    break
            continue

        # ----------------------------------------------------
        # ENCABEZADO
        # ----------------------------------------------------
        stdscr.attron(c_borde)
        stdscr.border(0)
        stdscr.attroff(c_borde)

        put(
            stdscr, 0, 2,
            " [ TERO-SDR : INTERFAZ TACTICA UGV ] ",
            c_borde | curses.A_BOLD
        )

        # ----------------------------------------------------
        # ESTADO DE COMUNICACIONES
        # ----------------------------------------------------
        if edad is None:
            enlace, c_enlace, extra = "SIN CONEXION", c_info, ""
        elif edad <= TIMEOUT_ENLACE_S:
            enlace, c_enlace = "ENLACE ACTIVO", c_ok
            extra = f"  (ultima trama hace {edad:.1f} s)"
        else:
            enlace, c_enlace = "ENLACE PERDIDO", c_alerta
            extra = f"  (ultima trama hace {edad:.0f} s)"
        activo = edad is not None and edad <= TIMEOUT_ENLACE_S

        campo(stdscr, 2, 3, "ENLACE    : ", enlace, c_enlace | curses.A_BOLD)
        put(stdscr, 2, 3 + 12 + len(enlace), extra, c_info)

        campo(stdscr, 3, 3, "TRAMAS RX : ", str(s["validos"]), c_ok)
        put(stdscr, 3, 25, "  |  ERRORES: ")
        put(stdscr, 3, 39, str(s["descartados"]),
            c_ok if s["descartados"] == 0 else c_info)

        stdscr.hline(4, 2, curses.ACS_HLINE | c_borde, ancho - 4)

        # ----------------------------------------------------
        # TELEMETRIA DE NAVEGACION
        # (con datos viejos se muestran en amarillo)
        # ----------------------------------------------------
        c_dato = c_ok if activo else c_info

        if datos is None:
            lat_t, lon_t = "--.---- -", "--.---- -"
            vel_t, rum_t = "--.- km/h", "--.- deg"
        else:
            lat, lon = datos["lat"], datos["lon"]
            lat_t = f"{abs(lat):08.4f} {'N' if lat >= 0 else 'S'}"
            lon_t = f"{abs(lon):08.4f} {'E' if lon >= 0 else 'W'}"
            vel_t = f"{datos['vel']:05.1f} km/h"
            rum_t = f"{datos['rumbo']:05.1f} deg"

        put(
            stdscr, 6, 3,
            "-- TELEMETRIA DE NAVEGACION --",
            c_borde | curses.A_BOLD
        )

        campo(stdscr, 8, 5, "LATITUD  : ", lat_t, c_dato)
        campo(stdscr, 9, 5, "LONGITUD : ", lon_t, c_dato)
        campo(stdscr, 10, 5, "VELOCIDAD: ", vel_t, c_dato)
        campo(stdscr, 11, 5, "RUMBO    : ", rum_t, c_dato)

        # ----------------------------------------------------
        # ESTADO DE PLATAFORMA
        # ----------------------------------------------------
        put(
            stdscr, 6, 38,
            "-- ESTADO DE PLATAFORMA --",
            c_borde | curses.A_BOLD
        )

        if datos is None:
            c_bat = c_info | curses.A_BOLD
            campo(stdscr, 8, 40, "BATERIA  : ", "---%", c_bat)
            campo(stdscr, 9, 40, "NIVEL    : ", "[" + "-" * 10 + "]", c_bat)
            campo(stdscr, 11, 40, "ESTADO   : ", "SIN DATOS", c_bat)
        else:
            bateria = datos["bateria"]
            critica = bateria < 25
            c_bat = (c_alerta if critica else c_dato) | curses.A_BOLD

            nivel = max(0, min(10, int(bateria / 10)))
            barra = "[" + "#" * nivel + "-" * (10 - nivel) + "]"
            estado_t = "CRITICO - CARGAR" if critica else "OPERATIVO [OK]"

            campo(stdscr, 8, 40, "BATERIA  : ", f"{bateria:03d}%", c_bat)
            campo(stdscr, 9, 40, "NIVEL    : ", barra, c_bat)
            campo(stdscr, 11, 40, "ESTADO   : ", estado_t, c_bat)

        # ----------------------------------------------------
        # CALIDAD DE SENAL (diagnostico del receptor)
        # ----------------------------------------------------
        corr = "--" if s["corr"] is None else f"{s['corr']:.2f}"
        cfo = "--" if s["cfo"] is None else f"{s['cfo']:+.0f} Hz"
        pico = "--" if s["pico"] is None else f"{s['pico']:.2f}"
        put(
            stdscr, 13, 3,
            f"SENAL  CORR: {corr} | CFO: {cfo} | PICO: {pico} | OVF: {s['overflows']}",
            c_info
        )

        # ----------------------------------------------------
        # PIE
        # ----------------------------------------------------
        stdscr.hline(14, 2, curses.ACS_HLINE | c_borde, ancho - 4)

        ultima = s["ts"] or "--"
        put(stdscr, 15, 3, f"FUENTE: SDR RX (DSSS)  |  ULTIMA TRAMA: {ultima}")
        put(stdscr, 16, 3, "Presione 'q' para salir.", c_info)

        stdscr.refresh()

        # ----------------------------------------------------
        # TECLADO (getch vuelve solo tras REFRESCO_MS -> redibuja)
        # ----------------------------------------------------
        tecla = stdscr.getch()

        if tecla in (ord("q"), ord("Q")):
            if confirmar_salida(stdscr, c_alerta):
                break


# ============================================================
# ARRANQUE: receptor en un hilo + pantalla en el hilo principal
# ============================================================
@contextmanager
def _stderr_a_null():
    """
    Mientras la pantalla esta activa, lo que escriban las librerias C por stderr
    (UHD, libhackrf) romperia el dibujo. Se descarta y se restaura al salir.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    guardado = os.dup(2)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(guardado, 2)
        os.close(guardado)
        os.close(devnull)


def correr_rx_con_pantalla(run_rx, driver, antena, ganancia):
    """
    Lanza run_rx() en un hilo y muestra la pantalla hasta que el usuario sale
    (tecla q + S, o Ctrl+C). No modifica la logica del receptor: solo le pasa
    el 'estado' (para informar) y el evento 'detener' (para pararlo).
    """
    locale.setlocale(locale.LC_ALL, "")
    estado = EstadoRX()
    detener = threading.Event()

    def trabajo():
        try:
            run_rx(driver, antena, ganancia, debug=False,
                   estado=estado, detener=detener)
        except BaseException as e:          # se re-lanza en el hilo principal
            estado.excepcion = e
        finally:
            estado.fin.set()

    hilo = threading.Thread(target=trabajo, name="rx", daemon=True)
    hilo.start()

    try:
        # El arranque del SDR imprime en la terminal normal; la pantalla
        # recien se abre cuando el SDR esta listo.
        while not estado.listo.is_set() and not estado.fin.is_set():
            estado.listo.wait(0.1)

        if estado.listo.is_set():
            with _stderr_a_null():
                curses.wrapper(interfaz, estado)
    except KeyboardInterrupt:
        pass
    finally:
        detener.set()
        print("\nRX detenido.", flush=True)
        hilo.join(timeout=5.0)    # run_rx imprime su resumen al cerrar

    if estado.excepcion is not None:
        raise estado.excepcion


# ============================================================
# VISTA PREVIA (sin SDR)
# ============================================================
def main():
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(interfaz, EstadoRX.demo())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
