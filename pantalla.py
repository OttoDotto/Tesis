
#!/usr/bin/env python3
import curses
import locale


# ============================================================
# DATOS DE EJEMPLO PARA LA VISTA PREVIA
# ============================================================
DATOS = {
    "lat": -34.6037,
    "lon": -58.3816,
    "vel": 12.5,
    "rumbo": 90.0,
    "bateria": 85,
}


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
        stdscr.timeout(-1)


# ============================================================
# INTERFAZ
# ============================================================
def interfaz(stdscr):
    curses.curs_set(0)
    stdscr.timeout(-1)

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
        campo(
            stdscr, 2, 3,
            "ENLACE    : ", "SIN CONEXION",
            c_info | curses.A_BOLD
        )

        campo(stdscr, 3, 3, "TRAMAS RX : ", "0", c_ok)
        put(stdscr, 3, 25, "  |  ERRORES: ")
        put(stdscr, 3, 39, "0", c_ok)

        stdscr.hline(4, 2, curses.ACS_HLINE | c_borde, ancho - 4)

        # ----------------------------------------------------
        # TELEMETRIA DE NAVEGACION
        # ----------------------------------------------------
        lat = DATOS["lat"]
        lon = DATOS["lon"]
        vel = DATOS["vel"]
        rumbo = DATOS["rumbo"]

        lat_t = f"{abs(lat):08.4f} {'N' if lat >= 0 else 'S'}"
        lon_t = f"{abs(lon):08.4f} {'E' if lon >= 0 else 'W'}"
        vel_t = f"{vel:05.1f} km/h"
        rum_t = f"{rumbo:05.1f} deg"

        put(
            stdscr, 6, 3,
            "-- TELEMETRIA DE NAVEGACION --",
            c_borde | curses.A_BOLD
        )

        campo(stdscr, 8, 5, "LATITUD  : ", lat_t, c_ok)
        campo(stdscr, 9, 5, "LONGITUD : ", lon_t, c_ok)
        campo(stdscr, 10, 5, "VELOCIDAD: ", vel_t, c_ok)
        campo(stdscr, 11, 5, "RUMBO    : ", rum_t, c_ok)

        # ----------------------------------------------------
        # ESTADO DE PLATAFORMA
        # ----------------------------------------------------
        bateria = DATOS["bateria"]
        bat_t = f"{bateria:03d}%"

        critica = bateria < 25
        c_bat = (c_alerta if critica else c_ok) | curses.A_BOLD

        put(
            stdscr, 6, 38,
            "-- ESTADO DE PLATAFORMA --",
            c_borde | curses.A_BOLD
        )

        campo(stdscr, 8, 40, "BATERIA  : ", bat_t, c_bat)

        nivel = int(bateria / 10)
        barra = "[" + "#" * nivel + "-" * (10 - nivel) + "]"
        estado = "CRITICO - CARGAR" if critica else "OPERATIVO [OK]"

        campo(stdscr, 9, 40, "NIVEL    : ", barra, c_bat)
        campo(stdscr, 11, 40, "ESTADO   : ", estado, c_bat)

        # ----------------------------------------------------
        # PIE
        # ----------------------------------------------------
        stdscr.hline(14, 2, curses.ACS_HLINE | c_borde, ancho - 4)

        put(stdscr, 15, 3, "FUENTE: TELEMETRIA DE NAVEGACION")
        put(stdscr, 16, 3, "Presione 'q' para salir.", c_info)

        stdscr.refresh()

        # ----------------------------------------------------
        # TECLADO
        # ----------------------------------------------------
        tecla = stdscr.getch()

        if tecla in (ord("q"), ord("Q")):
            if confirmar_salida(stdscr, c_alerta):
                break


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================
def main():
    locale.setlocale(locale.LC_ALL, "")

    try:
        curses.wrapper(interfaz)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
