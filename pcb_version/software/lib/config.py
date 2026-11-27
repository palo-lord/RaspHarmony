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

# Sustentação das teclas (anti-"picote"): depois de detectada, a tecla continua valendo por
# este tempo desde a ÚLTIMA detecção. Garante duração mínima da nota e evita que uma falha
# de 1 varredura (ruído, dedo no limite do limiar) solte e redispare a nota (novo ataque +
# martelada = som sujo). Aumente se ainda houver redisparos; diminua para notas mais curtas.
TECLA_SEGURA_MS = 100

# Mapeamentos padrão: tecla i (0..15) -> semitons acima do Dó da oitava atual.
# 0..11 = C..B da oitava, 12..23 = C..B da oitava seguinte, etc. (máx. MAPA_MAX)
# Os índices seguem o número do pad menos 1: índice 0 = pad 1 (último fisicamente)
# e índice 15 = pad 16 (primeiro fisicamente).
#
# Padrão 1 (um tom, cromático): pads 16..1 = F G A B | C C# D D# E | F F# G G# A A# B
#            pad:  1   2   3  4  5  6  7  8  9  10 11 12 13 14 15 16
_MAPA_1 = (11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 9, 7, 5)
# Padrão 2 (dois tons, escala de Dó maior): pads 16..9 no tom atual, 8 (Ré) também,
# pads 7..1 no tom seguinte.
#            pad:  1   2   3   4   5   6   7  8  9  10 11 12 13 14 15 16
_MAPA_2 = (23, 21, 19, 17, 16, 14, 12, 2, 0, 11, 9, 7, 5, 4, 2, 0)
MAPAS_PADRAO = (_MAPA_1, _MAPA_2)
MAPA_PADRAO = MAPAS_PADRAO[0]   # padrão de partida
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
SD_BAUD = 12000000   # velocidade do SD após a inicialização. Era 1,32 MHz (~165 KB/s úteis no máximo, e menos
                     # com o overhead do Python): não sustentava nem um WAV estéreo de 32 kHz (128 KB/s),
                     # daí o picote. Se o cartão der erro de leitura (OSError 5) ou não montar, tente
                     # 8000000 ou 4000000.
TAM_BUFFER = 4096    # bytes lidos por vez do SD (múltiplo de 512). Era 8192, mas faltava um bloco
                     # contíguo de RAM para ele depois do buffer do I2S (MemoryError). Deve ficar bem abaixo de IBUF_PLAYER
REPETIR_LISTA = True

# Estados do Player
PARADO, TOCANDO, PAUSADO = 0, 1, 2

# Áudio / I2S
SAMPLE_RATE = 44100          # sintetizador (teclado)
SAMPLE_RATE_PLAYER = 44100   # Player: I2S abre a 44,1 kHz (se o WAV tiver outra taxa, o audio.py reabre na taxa do arquivo)
IBUF_SINT = 6144     # ~70 ms de latência no teclado (era 4096 = ~46.5 ms; mais folga contra
                     # estalos de buffer vazio, enquanto a varredura do toque/OLED ocupa a CPU)
SINT_MARGEM_BLOCOS = 3   # blocos de sobra gerados a cada varredura do teclado (ver app.py)
SINT_BLOCOS_MAX = 12     # máx. de blocos por volta (12 x 256 amostras = IBUF_SINT inteiro)
IBUF_PLAYER = 16384  # ~186 ms de folga (mono). 32768 falha com MemoryError (heap fragmentado)

# Volume
VOL_PASSO = 2        # % por clique do encoder
VOLUME_INICIAL = 16

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
