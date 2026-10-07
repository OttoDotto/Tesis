#!/usr/bin/env python3
import curses
import locale
import random
import socket
import struct
import sys
import threading
import time

FORMATO_PAQUETE = "<ffffH"
UDP_HOST = "127.0.0.1"
UDP_PORT = 5005
TIMEOUT_ENLACE_S = 3.0
REFRESCO_MS = 200


# ============================================================
# FUENTE SIMULADA: hace de "programa del SDR" (manda por UDP)
# ============================================================
def generar_paquete_ejemplo():
    return struct.pack(
        FORMATO_PAQUETE,
        random.uniform(-34.5000, -34.7000),
        random.uniform(-58.3000, -58.5000),
        random.uniform(0.0, 45.0),
        random.uniform(0.0, 359.9),
        random.randint(10, 100),
    )


class SimuladorSDR(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.detener = threading.Event()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while not self.detener.is_set():
            paquete = generar_paquete_ejemplo()
            try:
                sock.sendto(paquete, (UDP_HOST, UDP_PORT))
            except OSError:
                pass
            self.detener.wait(random.uniform(0.5, 1.5))
        sock.close()


# ============================================================
# RECEPTOR: lo unico que usa la interfaz (sim o real)
# ============================================================
class ReceptorUDP:
    def __init__(self, host, puerto):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, puerto))  # falla si ya hay otra pantalla abierta
        self.sock.setblocking(False)

    def leer_pendientes(self):
        """Devuelve todos los paquetes que llegaron desde la ultima lectura."""
        paquetes = []
        while True:
            try:
                datos, _ = self.sock.recvfrom(1024)
            except BlockingIOError:
                break
            paquetes.append(datos)
        return paquetes

    def cerrar(self):
        self.sock.close()


# ============================================================
# UTILIDADES DE DIBUJO
# ============================================================
def put(win, y, x, texto, attr=0):
    """addstr que nunca revienta si algo no entra en pantalla."""
    try:
        win.addstr(y, x, texto, attr)
    except curses.error:
        pass


def campo(win, y, x, etiqueta, valor, attr):
    put(win, y, x, etiqueta)
    put(win, y, x + len(etiqueta), valor, attr)


def confirmar_salida(stdscr, c_alerta):
    """Solo acepta S (salir) o N/Esc (cancelar). Cualquier otra tecla se ignora."""
    msg = "  ¿DESEA SALIR DE LA INTERFAZ? [S/N]  "
    attr = c_alerta | curses.A_REVERSE | curses.A_BOLD
    stdscr.timeout(-1)  # bloqueante mientras dura el dialogo
    try:
        while True:
            alto, ancho = stdscr.getmaxyx()
            y = alto // 2
            x = max(0, (ancho - len(msg)) // 2)
            put(stdscr, y - 1, x, " " * len(msg), attr)
            put(stdscr, y,     x, msg, attr)
            put(stdscr, y + 1, x, " " * len(msg), attr)
            stdscr.refresh()
            tecla = stdscr.getch()
            if tecla in (ord('s'), ord('S')):
                return True
            if tecla in (ord('n'), ord('N'), 27):
                return False
    finally:
        stdscr.timeout(REFRESCO_MS)


# ============================================================
# INTERFAZ
# ============================================================
def interfaz(stdscr, receptor, modo_sim):
    curses.curs_set(0)
    stdscr.timeout(REFRESCO_MS)

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()  # usa el fondo real de la terminal
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

    c_ok = curses.color_pair(1)
    c_borde = curses.color_pair(2)
    c_alerta = curses.color_pair(3)
    c_info = curses.color_pair(4)

    rx_ok = 0
    rx_err = 0
    ultimo = None      # (lat, lon, vel, rumbo, bateria)
    t_ultimo = None    # instante del ultimo paquete valido

    while True:
        # --- Teclado: solo 'q' hace algo ---
        tecla = stdscr.getch()
        if tecla in (ord('q'), ord('Q')):
            if confirmar_salida(stdscr, c_alerta):
                break

        # --- Datos: solo cuenta lo que realmente llego ---
        for datos in receptor.leer_pendientes():
            try:
                ultimo = struct.unpack(FORMATO_PAQUETE, datos)
                t_ultimo = time.monotonic()
                rx_ok += 1
            except struct.error:
                rx_err += 1

        # --- Dibujo ---
        stdscr.erase()
        alto, ancho = stdscr.getmaxyx()

        if alto < 18 or ancho < 65:
            put(stdscr, 0, 0, "AMPLIAR TERMINAL (Minimo: 65x18)"[:max(0, ancho - 1)], c_info)
            stdscr.refresh()
            continue

        # Estado del enlace
        if t_ultimo is None:
            enlace_txt, c_enlace = "ESPERANDO DATOS...", c_info
            ultimo_txt = "--"
        else:
            edad = time.monotonic() - t_ultimo
            ultimo_txt = f"hace {edad:.1f} s"
            if edad > TIMEOUT_ENLACE_S:
                enlace_txt, c_enlace = "ENLACE PERDIDO", c_alerta | curses.A_BOLD
            else:
                enlace_txt, c_enlace = "ENLACE ACTIVO", c_ok | curses.A_BOLD

        stdscr.attron(c_borde)
        stdscr.border(0)
        stdscr.attroff(c_borde)
        put(stdscr, 0, 2, " [ TERO-SDR : INTERFAZ TACTICA UGV ] ", c_borde | curses.A_BOLD)
        tag = " [MODO-SIM] " if modo_sim else " [MODO-REAL] "
        put(stdscr, 0, ancho - len(tag) - 2, tag, c_info | curses.A_BOLD)

        campo(stdscr, 2, 3, "ENLACE    : ", enlace_txt, c_enlace)
        campo(stdscr, 3, 3, "TRAMAS RX : ", f"{rx_ok}", c_ok)
        put(stdscr, 3, 3 + 12 + len(str(rx_ok)), "  |  ERRORES: ")
        put(stdscr, 3, 3 + 12 + len(str(rx_ok)) + 13, f"{rx_err}",
            c_alerta if rx_err else c_ok)
        put(stdscr, 3, 3 + 12 + len(str(rx_ok)) + 13 + len(str(rx_err)),
            f"  |  ULTIMO: {ultimo_txt}")
        stdscr.hline(4, 2, curses.ACS_HLINE | c_borde, ancho - 4)

        # Valores (o placeholders si todavia no llego nada)
        if ultimo is None:
            lat_t = lon_t = vel_t = rum_t = bat_t = "--"
            bateria = None
        else:
            lat, lon, vel, rumbo, bateria = ultimo
            lat_t = f"{abs(lat):08.4f} {'N' if lat >= 0 else 'S'}"
            lon_t = f"{abs(lon):08.4f} {'E' if lon >= 0 else 'W'}"
            vel_t = f"{vel:05.1f} km/h"
            rum_t = f"{rumbo:05.1f} deg"
            bat_t = f"{bateria:03d}%"

        critica = bateria is not None and bateria < 25
        c_bat = (c_alerta if critica else c_ok) | curses.A_BOLD

        put(stdscr, 6, 3, "-- TELEMETRIA DE NAVEGACION --", c_borde | curses.A_BOLD)
        campo(stdscr, 8, 5,  "LATITUD  : ", lat_t, c_ok)
        campo(stdscr, 9, 5,  "LONGITUD : ", lon_t, c_ok)
        campo(stdscr, 10, 5, "VELOCIDAD: ", vel_t, c_ok)
        campo(stdscr, 11, 5, "RUMBO    : ", rum_t, c_ok)

        put(stdscr, 6, 38, "-- ESTADO DE PLATAFORMA --", c_borde | curses.A_BOLD)
        campo(stdscr, 8, 40, "BATERIA  : ", bat_t, c_bat)
        if bateria is None:
            barra, estado = "[----------]", "--"
        else:
            n = int(max(0, min(100, bateria)) / 10)
            barra = "[" + "#" * n + "-" * (10 - n) + "]"
            estado = "CRITICO - CARGAR" if critica else "OPERATIVO [OK]"
        campo(stdscr, 9, 40, "NIVEL    : ", barra, c_bat)
        campo(stdscr, 11, 40, "ESTADO   : ", estado, c_bat)

        stdscr.hline(14, 2, curses.ACS_HLINE | c_borde, ancho - 4)
        fuente = f"UDP {UDP_HOST}:{UDP_PORT}" + (" (simulada)" if modo_sim else "")
        put(stdscr, 15, 3, f"FUENTE: {fuente}")
        put(stdscr, 16, 3, "Presione 'q' para salir.", c_info)

        stdscr.refresh()


def main():
    locale.setlocale(locale.LC_ALL, "")
    modo_sim = "--real" not in sys.argv

    try:
        receptor = ReceptorUDP(UDP_HOST, UDP_PORT)
    except OSError as e:
        print(f"No se pudo abrir el puerto UDP {UDP_PORT}: {e}")
        print("¿Hay otra interfaz abierta?")
        sys.exit(1)

    simulador = None
    if modo_sim:
        simulador = SimuladorSDR()
        simulador.start()

    try:
        curses.wrapper(interfaz, receptor, modo_sim)
    except KeyboardInterrupt:
        pass
    finally:
        if simulador:
            simulador.detener.set()
        receptor.cerrar()


if __name__ == "__main__":
    main()