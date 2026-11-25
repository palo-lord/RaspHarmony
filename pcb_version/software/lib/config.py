# ============================================================
# config.py - Pinos, constantes e tabelas de configuração (versão PCB)
# ============================================================

# Botões de Navegação (ativos em nível baixo, com pull-up interno)
pin_Nav_U = 12
pin_Nav_R = 1
pin_Nav_L = 13
pin_Nav_D = 15
pin_Nav_Ok = 14

# Encoder Rotativo (só giro = volume; o botão do encoder não é usado)
pin_ENC_A = 26
pin_ENC_B = 27

# MAX98357 - I2S
WS_PIN = 7   # Word Select (LRCK) - LRC
SCK_PIN = 6  # Serial Clock (BCLK)
SD_PIN = 5   # Serial Data (DIN / DOUT)

# I2C Expansor (MCP23017, 16 pads do teclado de toque)
Exp_SCL = 11
Exp_SDA = 10
Exp_RST = 9      # RESET do MCP23017 (ativo em nível baixo)
Exp_INT = 8      # INT (não usado)
EXP_I2C_ID = 1   # GP10/GP11 = I2C1
EXP_I2C_FREQ = 400000   # 1000000 deixa a varredura ~2x mais rápida (o MCP23017 aceita até 1,7 MHz)
EXP_ADDR = 0x20

# Teclado de toque capacitivo (ver toque.py)
N_TECLAS = 16
TOQUE_PULLUP = False      # True: resistor de 1 MΩ de cada pad para 3V3 (mede o tempo de SUBIDA).
                         # False: resistor para GND (mede o tempo de DESCIDA) (Pulldown).
TOQUE_AMOSTRAS = 3       # ciclos carga/descarga por varredura (a média reduz o ruído)
TOQUE_DITHER_US = 35     # atraso extra entre ciclos (µs) para melhorar a resolução do tempo
TOQUE_LEITURAS = 6       # leituras I2C por ciclo (tempo máx. de carga ≈ leituras x ~100 µs)
TOQUE_LIMIAR_US = 50     # acima da linha de base por mais que isso = tocado
TOQUE_T_MAX_US = 2000    # tempo atribuído a um pad que não carregou dentro das leituras

# Mapeamento padrão: tecla i (0..15) -> semitons acima do Dó da oitava atual.
# 0..11 = C..B da oitava, 12..23 = C..B da oitava seguinte, etc. (máx. MAPA_MAX)
MAPA_PADRAO = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
MAPA_MAX = 35

# Display OLED 2,42"/2,45" SSD1309 (SPI)
OLED_W = 128
OLED_H = 64
OLED_SCK, OLED_MOSI, OLED_CS = 18, 19, 22
OLED_RES = 20
OLED_DC = 21
# GP18/GP19 e GP0/GP2/GP3 (SD) são pinos do MESMO SPI0 de hardware. O módulo spibus.py
# reconfigura o SPI0 para os pinos de cada dispositivo (o SD é o estado de repouso).
OLED_BAUD = 8000000
OLED_ROTACAO = 0         # 0 ou 180, conforme a montagem do display

# Cartão SD (SPI0)
SD_MOUNT = "/sd"
SD_SCK, SD_MOSI, SD_MISO, SD_CS = 2, 3, 0, 4
SD_BAUD = 1320000    # velocidade do SD após a inicialização (valor padrão do sdcard.py);
                     # se o cartão aguentar, tente 4000000 ou mais para folgar no Player
TAM_BUFFER = 8192    # bytes lidos por vez do SD (múltiplo de 512 é ideal), 93ms
REPETIR_LISTA = True

# Estados do Player
PARADO, TOCANDO, PAUSADO = 0, 1, 2

# Áudio / I2S
SAMPLE_RATE = 44100
IBUF_SINT = 4096     # ~46.5 ms de latência no teclado
IBUF_PLAYER = 16384   # ~186 ms de folga (mono). 32768 falha com MemoryError (heap fragmentado)

# Volume
VOL_PASSO = 2        # % por clique do encoder
VOLUME_INICIAL = 30

# Botões de navegação
NAV_DEBOUNCE_MS = 30     # ignora repiques depois de uma borda
NAV_LONGO_MS = 500       # apertar e soltar antes disso = clique curto; depois = "segurando"
NAV_REPETE_MS = 300      # intervalo de repetição enquanto segura
PULO_S = 5               # segundos que o Player pula a cada repetição (Left/Right segurado)

# Oitava do teclado (Left/Right no modo Instrumento)
OITAVA_MIN, OITAVA_MAX = 3, 5

# Interface - UI
# O índice 4 (Acordes) é preenchido em estado.py, pois depende da lista de acordes.
MODES = [
    ["Teclado", "Player"],                                           # 0: Menu Principal
    ["Instrumento", "Acordes", "Afinador", "Mapeamento", "Menu"],    # 1: Modo Teclado
    ["Player", "Menu"],                                              # 2: Modo Player
    ["Piano", "Sintetizador", "Teclado"],                            # 3: Modo Instrumento
    ["Teclado"],                                                     # 4: Modo Acordes
    ["Zerar", "Teclado"],                                            # 5: Modo Afinador
    ["Tecla", "Nota", "Padrao", "Teclado"]]                          # 6: Mapeamento das teclas

DURACAO_ACORDE_MS = 1500
DURACAO_PREVIA_MS = 600  # som de prévia ao mudar a nota no Mapeamento
UI_MIN_MS = 150          # intervalo mínimo entre redesenhos da tela

# Afinador
PASSO_CENTS = 1      # cents por clique do encoder
LIM_CENTS = 50       # afinação limitada a +-50 cents

