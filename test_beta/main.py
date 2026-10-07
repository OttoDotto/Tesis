import argparse
import sys
from TX import run_tx
from RX import run_rx

def main():
    parser = argparse.ArgumentParser(description="Sistema de Telemetria BPSK")
    
    parser.add_argument('-m', '--mode', type=str, choices=['tx', 'rx'], required=True, 
                        help="Modo de operacion: 'tx' o 'rx'")
    parser.add_argument('-d', '--driver', type=str, choices=['uhd', 'hackrf'], required=True, 
                        help="SDR a utilizar: 'uhd' (Ettus) o 'hackrf'")
    parser.add_argument('-a', '--antenna', type=str, required=True, 
                        help="Antena a utilizar (ej. 'TX/RX', 'RX2', 'RX', 'TX')")
    parser.add_argument('-g', '--gain', type=int, required=True, 
                        help="Ganancia general a configurar en el SDR (ej. 40)")
    parser.add_argument('--debug', action='store_true', 
                        help="Activar trazas detalladas de bajo nivel (Modo Debug)")

    args = parser.parse_args()

    driver_str = f"driver={args.driver}"
    antena_str = args.antenna
    ganancia_str = args.gain
    debug_mode = args.debug

    print("============================================")
    print("INICIANDO SISTEMA SDR DE TELEMETRIA")
    print(f"Modo    : {args.mode.upper()}")
    print(f"Driver  : {driver_str}")
    print(f"Antena  : {antena_str}")
    print(f"Ganancia: {ganancia_str}")
    print(f"Debug   : {'ACTIVADO' if debug_mode else 'DESACTIVADO (Modo Limpio)'}")
    print("============================================\n")

    if args.mode == 'tx':
        run_tx(driver_str, antena_str, ganancia_str, debug=debug_mode)
    elif args.mode == 'rx':
        run_rx(driver_str, antena_str, ganancia_str, debug=debug_mode)

if __name__ == "__main__":
    main()