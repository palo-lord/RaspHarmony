# ============================================================
# config.py - Pinos, constantes e tabelas de configuração
# ============================================================

# Joystick Analógico
pin_JOY_X = 26
pin_JOY_Y = 27
pin_JOY_SW = 28

# Encoder Rotativo
pin_ENC_A = 13
pin_ENC_B = 14
pin_ENC_SW = 15

# MAX98357 - I2S
WS_PIN = 22   # Word Select (LRCK) - LRC
SCK_PIN = 21  # Serial Clock (BCLK)
SD_PIN = 20   # Serial Data (DIN / DOUT)

# Teclado matricial
row_pins = [12, 11, 10, 9]  # R1, R2, R3, R4
col_pins = [8, 7, 6, 5]     # C1, C2, C3, C4

# Mapeamento das teclas e notas do keypad 4x4
key_notes = [
    ["C", "C#", "D", "D#"],
    ["E", "F", "F#", "G"],
    ["G#", "A", "A#", "B"],
    ["Reinicia", "Prev", "Play/Stop", "Next"]]

# Display OLED (I2C)
OLED_W = 128
OLED_H = 64
OLED_SCL = 1
OLED_SDA = 0
OLED_ADDR = 0x3C

# Joystick
INVERTE_X = False    # troque para True se o joystick navegar ao contrário
INVERTE_Y = False
LIMIAR = 12000       # sensibilidade para detectar movimento

# Cartão SD (SPI)
SD_MOUNT = "/sd"
SD_SCK, SD_MOSI, SD_MISO, SD_CS = 18, 19, 16, 17
TAM_BUFFER = 8192    # bytes lidos por vez do SD (múltiplo de 512 é ideal)
REPETIR_LISTA = True

# Estados do Player
PARADO, TOCANDO, PAUSADO = 0, 1, 2

# Áudio / I2S
SAMPLE_RATE = 44100
IBUF_SINT = 4096     # ~93 ms de latência no teclado
IBUF_PLAYER = 16384   # ~186 ms: folga para o display atualizar sem falhar o áudio

# Volume
VOL_PASSO = 5        # % por clique do encoder
VOLUME_INICIAL = 50

# Interface - UI
# O índice 4 (Acordes) é preenchido em estado.py, pois depende da lista de acordes.
MODES = [
    ["Teclado", "Player"],                          # 0: Menu Principal
    ["Instrumento", "Acordes", "Afinador", "Menu"], # 1: Modo Teclado
    ["Menu"],                                       # 2: Modo Player
    ["Piano", "Sintetizador", "Teclado"],           # 3: Modo Instrumento
    ["Teclado"],                                    # 4: Modo Acordes
    ["Teclado"]]                                    # 5: Modo Afinador
ESTADO_UI = ["Menu", "Teclado", "Player", "Instrumento", "Acordes", "Afinador"]

DURACAO_ACORDE_MS = 1500

# Afinador
PASSO_CENTS = 1      # cents por clique do encoder
LIM_CENTS = 50       # afinação limitada a +-50 cents

# Grade vertical do display
Y_INI = 11
Y_PASSO = 9
Y_NOTAS = 47
Y_RODAPE = 56
