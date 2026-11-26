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
EXP_I2C_FREQ = 400000   # máximo especificado do MCP23017 a 3V3 (1 MHz só vale com 4,5-5,5 V e pull-ups fortes)
EXP_ADDR = 0x20

# Teclado de toque capacitivo (ver toque.py)
N_TECLAS = 16
# Medição (amostragem em tempo equivalente: 1 leitura por ciclo, atraso crescente)
TOQUE_CARGA_US = 20      # tempo com os pads como saída em nível alto antes de soltar (carga)
TOQUE_PASSO_US = 8       # resolução: incremento do atraso entre ciclos (µs)
TOQUE_JANELA_AUTO = True # calibração posiciona a janela em volta dos pads livres
TOQUE_ATRASO0_US = 0     # início da janela (µs) - só usado se TOQUE_JANELA_AUTO = False
TOQUE_PASSOS = 16        # ciclos por varredura - só usado se TOQUE_JANELA_AUTO = False
TOQUE_PASSOS_MAX = 20    # limite de ciclos com janela automática (cada ciclo ≈ 0,4 ms a 400 kHz)
TOQUE_FOLGA_US = 64      # janela além do pad livre mais lento (espaço para o dedo)
TOQUE_REPETICOES = 1     # varreduras somadas por medição (2 = menos ruído, 2x mais lento)
TOQUE_T_MAX_US = 1500    # limite da busca grossa da calibração (pad que não cai = defeito)
TOQUE_SEM_IRQ = True     # desliga IRQs entre soltar e ler (atraso exato, menos jitter)
# Modo INT: o pino INT do MCP23017 (Exp_INT) vira o "cronômetro" da descarga.
# Mede o tempo entre soltar o pad e a borda do INT (resolução ~1 µs, não depende do I2C).
# Mede 1 pad por vez (varredura ~10 ms). Se False, usa o método antigo (leitura I2C).
TOQUE_USAR_INT = True
TOQUE_INT_TIMEOUT_US = 300   # tempo máximo esperando o INT (acima disso o pad é "defeito")
# Detecção (com TOQUE_USAR_INT = True os tempos são em µs reais, por isso limiar pequeno;
# no método antigo use TOQUE_LIMIAR_US = 24)
TOQUE_LIMIAR_US = 3      # mínimo acima da linha de base para considerar tocado
TOQUE_K_RUIDO = 3        # limiar do pad = max(TOQUE_LIMIAR_US, K x ruído da calibração)
TOQUE_SOLTAR_PCT = 60    # histerese: solta quando cai abaixo de 60% do limiar
TOQUE_CICLOS_CAL = 16    # medições usadas na calibração
TOQUE_PRESO_MS = 30000   # pad "tocado" por mais que isso é recalibrado (0 = desliga)

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
VOLUME_INICIAL = 15

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
