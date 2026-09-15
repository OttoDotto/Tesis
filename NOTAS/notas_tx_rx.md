TX inicia
  │
  ├── genera PN
  │
  ├── ¿USAR_SDR?
  │       │
  │       ├── SI → abre SDR
  │       │
  │       └── NO → guarda PN en datos/
  │
  ▼
Loop
  │
  ├── obtiene datos
  ├── Hamming
  ├── DSSS
  ├── preámbulo
  ├── pulse shaping
  │
  └── ¿USAR_SDR?
          │
          ├── SI → transmite por SDR
          │
          └── NO → guarda .npy
  │
  ▼
Ctrl+C
  │
  ├── cierra SDR si corresponde
  └── limpia archivos de simulación si corresponde

--- 
ahora:
TX                                  RX

preparar_pn()                       preparar_pn()
preparar_serial()                   preparar_preambulo()
preparar_sdr()
       │                                  │
       ▼                                  ▼
 ejecutar_tx()                       ejecutar_rx()
       │                                  │
       ├─ obtener datos                    ├─ obtener señal
       ├─ generar trama                    ├─ procesar señal
       ├─ mostrar info                     ├─ mostrar datos
       └─ transmitir                       └─ estadísticas