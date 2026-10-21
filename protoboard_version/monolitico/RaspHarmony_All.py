# ============================================================
# RaspHarmony - Sistema Embarcado Sintetizador e Reprodutor de Áudio
# ============================================================
# Nome: Paulo Sergio Gonçalves Júnior RA: 218474
# Nome: Vinicius Pedrillo de Souza RA: 258667
# ============================================================
# Versão adaptada para o display OLED 128x64 (SSD1306).
# ============================================================

from machine import Pin, PWM, ADC, I2C, SPI, I2S, disable_irq, enable_irq
from sh1106 import SH1106_I2C
import utime
import math
import array
import os
import struct
import time
import sdcard
import micropython
import gc

micropython.alloc_emergency_exception_buf(100)  # permite ver erros dentro de IRQ

# Tabela de decodificação em quadratura.
# Índice = (estado_anterior << 2) | estado_novo, com estado = (A << 1) | B.
_TAB_ENC = (0, 1, -1, 0,
            -1, 0, 0, 1,
            1, 0, 0, -1,
            0, -1, 1, 0)

class Encoder:
    """Encoder rotativo em quadratura. A interrupção só acumula passos;
    o resto do programa lê com cliques(), sem nunca mexer em SD/I2S/OLED na IRQ."""

    def __init__(self, pino_a, pino_b, passos_por_clique=4):
        self.a = pino_a
        self.b = pino_b
        self.ppc = passos_por_clique      # 4 para a maioria (KY-040); 2 ou 1 em outros
        self.estado = (self.a.value() << 1) | self.b.value()
        self.contagem = 0
        gatilho = Pin.IRQ_RISING | Pin.IRQ_FALLING
        self.a.irq(trigger=gatilho, handler=self._irq, hard=True)
        self.b.irq(trigger=gatilho, handler=self._irq, hard=True)

    def _irq(self, pino):
        novo = (self.a.value() << 1) | self.b.value()
        self.contagem += _TAB_ENC[(self.estado << 2) | novo]
        self.estado = novo

    def cliques(self):
        """Retorna os 'cliques' (detents) desde a última chamada:
        positivo = horário, negativo = anti-horário. Troque o sinal se o
        seu encoder estiver ligado ao contrário."""
        st = disable_irq()
        c = self.contagem
        n = c // self.ppc if c >= 0 else -((-c) // self.ppc)
        self.contagem = c - n * self.ppc   # guarda o resto de um clique incompleto
        enable_irq(st)
        return n


class Botao:
    """Botão com detecção de borda (um único evento por aperto) e debounce
    por tempo, SEM sleep: não trava o áudio."""

    def __init__(self, pino, debounce_ms=250):
        self.pino = pino
        self.deb = debounce_ms
        self.ant = pino.value()
        self.t = utime.ticks_ms()

    def pressionado(self):
        v = self.pino.value()
        agora = utime.ticks_ms()
        evento = False
        if v == 0 and self.ant == 1 and utime.ticks_diff(agora, self.t) > self.deb:
            evento = True
            self.t = agora
        self.ant = v
        return evento


# ===================== Inicialização ========================
# Joystick Analógico ------------------------------
pin_JOY_X = 26
pin_JOY_Y = 27
pin_JOY_SW = 28

# Encoder Rotativo --------------------------------
pin_ENC_A = 13
pin_ENC_B = 14
pin_ENC_SW = 15

# MAX98357 - I2S  ---------------------------------
WS_PIN = 22   # Word Select (LRCK)- LRC
SCK_PIN = 21  # Serial Clock (BCLK)
SD_PIN = 20   # Serial Data (DIN /DOUT)

# Teclado  ----------------------------------------
row_pins = [12, 11, 10, 9] # R1, R2, R3, R4
col_pins = [8, 7, 6, 5]   # C1, C2, C3, C4

# Mapeamento das teclas e notas do keypad 4x4 -----
key_notes = [
    ["C", "C#", "D", "D#"],
    ["E", "F", "F#", "G"],
    ["G#", "A", "A#", "B"],
    ["Reinicia", "Prev", "Play/Stop", "Next"]]

# Interface - UI  ---------------------------------
MODES = [
    ["Teclado", "Player"],                          # 0: Menu Principal
    ["Instrumento", "Acordes", "Afinador", "Menu"], # 1: Modo Teclado
    ["Menu"],                                       # 2: Modo Player
    ["Piano", "Sintetizador", "Teclado"],           # 3: Modo Instrumento
    ["Teclado"],                                    # 4: Modo Acordes (lista é montada mais abaixo)
    ["Teclado"]]                                    # 5: Modo Afinador
ESTADO_UI = ["Menu", "Teclado", "Player", "Instrumento", "Acordes", "Afinador"]
mode_ui = 0 # Interface Inicial
mode_sel = 0

# ===================== Configurações ========================

# Joystick Analógico -----------------------------------------
joy_sw = Pin(pin_JOY_SW, Pin.IN, Pin.PULL_UP)
joy_x = ADC(Pin(pin_JOY_X))
joy_y = ADC(Pin(pin_JOY_Y))
btn_joy = Botao(joy_sw)
INVERTE_X = False    # troque para True se o joystick navegar ao contrário
INVERTE_Y = False

utime.sleep_ms(100) # Calibracao do centro do joystick
centro_x = joy_x.read_u16()
centro_y = joy_y.read_u16()
LIMIAR = 12000       # sensibilidade para detectar movimento
zona_neutra_x = True
zona_neutra_y = True

# Encoder Rotativo -------------------------------------------
enc_a = Pin(pin_ENC_A, Pin.IN, Pin.PULL_UP)
enc_b = Pin(pin_ENC_B, Pin.IN, Pin.PULL_UP)
enc_sw = Pin(pin_ENC_SW, Pin.IN, Pin.PULL_UP)

enc = Encoder(enc_a, enc_b)
btn_enc = Botao(enc_sw)

# Teclado ------------------ ---------------------------------
rows = [Pin(pin, Pin.OUT) for pin in row_pins]
cols = [Pin(pin, Pin.IN, Pin.PULL_DOWN) for pin in col_pins]

# Display OLED - I2C (128x64) --------------------------------
# Cada oled.show() envia 1 KB (128x64 / 8). Se quiser atualizar mais rápido, tente freq=1000000.
OLED_W = 128
OLED_H = 64
i2c_oled = I2C(0, scl=Pin(1), sda=Pin(0), freq=400000)
oled = SH1106_I2C(OLED_W, OLED_H, i2c_oled, addr=0x3C, rotate=180)

# Cartão SD - SPI --------------------------------------------
SD_MOUNT = "/sd"
TAM_BUFFER = 2048 # bytes lidos por vez do SD (múltiplo de 512 é ideal)
REPETIR_LISTA = True

spi_SD = SPI(0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16)
)
cs = Pin(17, Pin.OUT)
cs.value(1) # Desativa o dispositivo inicialmente

# Se o cartão não estiver presente, o Teclado continua funcionando
# (só o Player fica sem faixas).
try:
    sd = sdcard.SDCard(spi_SD, cs)
    try:
        os.mount(sd, SD_MOUNT)
    except OSError:
        pass  # já montado
    ARQUIVOS = [SD_MOUNT + "/" + nome for nome in sorted(os.listdir(SD_MOUNT))
                if nome.lower().endswith(".wav")]
except Exception as e:
    print("SD indisponivel:", e)
    ARQUIVOS = []
PARADO, TOCANDO, PAUSADO = 0, 1, 2

# I2S para saída de áudio (MAX98357A) -----------------------------------
SAMPLE_RATE = 16000
IBUF_SINT = 4096      # ~93 ms de latência no teclado (menor = mais rápido, mas o display pode causar falhas)
IBUF_PLAYER = 8192    # ~186 ms: folga para o display atualizar sem falhar o áudio
i2s_max = None
_cfg_i2s = None


def abrir_i2s(taxa, canais, ibuf):
    """(Re)cria o I2S só se a configuração mudou."""
    global i2s_max, _cfg_i2s
    cfg = (taxa, canais, ibuf)
    if cfg == _cfg_i2s:
        return
    if i2s_max is not None:
        i2s_max.deinit()
    i2s_max = I2S(0,
        sck=Pin(SCK_PIN),
        ws=Pin(WS_PIN),
        sd=Pin(SD_PIN),
        mode=I2S.TX,
        rate=taxa,
        bits=16,
        format=I2S.STEREO if canais == 2 else I2S.MONO,
        ibuf=ibuf)
    _cfg_i2s = cfg


abrir_i2s(SAMPLE_RATE, 1, IBUF_SINT)
SILENCIO = bytearray(512)

# ===================== Funções ========================

def key_notes_scan(flag_teclado):
    if flag_teclado:
        List = []
        for r_idx, row in enumerate(rows):
            if (r_idx == 3):
                # No modo teclado varre as 3 primeiras linhas
                continue
            row.high()
            for c_idx, col in enumerate(cols):
                if col.value() == 1:
                    List.append(key_notes[r_idx][c_idx])
            row.low()
        return List

    else: # Player
        for r_idx, row in enumerate(rows):
            if not (r_idx == 3):
                # No modo player varre a última linha
                continue
            row.high()
            for c_idx, col in enumerate(cols):
                if col.value() == 1:
                    row.low()
                    return key_notes[r_idx][c_idx]
            row.low()
    return None

def joystick_sense(): # ---------- Leitura do joystick ----------
    """Retorna (x, movimento_x, movimento_y).
    x = desvio analógico em X (para o 'pular' do Player);
    movimento_x/y = -1, 0 ou +1, UM evento por empurrão (com histerese)."""
    global zona_neutra_x, zona_neutra_y
    raw_x = joy_x.read_u16()
    raw_y = joy_y.read_u16()
    x = centro_x - raw_x
    y = centro_y - raw_y
    if INVERTE_X:
        x = -x
    if INVERTE_Y:
        y = -y

    movimento_x = 0
    movimento_y = 0

    if zona_neutra_x:
        if x > LIMIAR:
            movimento_x = 1
            zona_neutra_x = False
        elif x < -LIMIAR:
            movimento_x = -1
            zona_neutra_x = False
    else:
        if abs(x) < LIMIAR // 3:
            zona_neutra_x = True

    if zona_neutra_y:
        if y > LIMIAR:
            movimento_y = 1
            zona_neutra_y = False
        elif y < -LIMIAR:
            movimento_y = -1
            zona_neutra_y = False
    else:
        if abs(y) < LIMIAR // 3:
            zona_neutra_y = True

    return (x, movimento_x, movimento_y)

class WavFile:
    """Abre um WAV, interpreta o cabeçalho e permite ler os dados em blocos."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.f = open(caminho, "rb")
        self.formato = 0
        self.canais = 0
        self.taxa = 0
        self.bits = 0
        self.data_inicio = 0
        self.data_tamanho = 0
        self.restante = 0
        try:
            self._ler_cabecalho()
        except Exception:
            self.f.close()
            raise

    def _ler_cabecalho(self):
        f = self.f
        cab = f.read(12)
        if len(cab) < 12 or cab[0:4] != b"RIFF" or cab[8:12] != b"WAVE":
            raise ValueError("Não é um arquivo WAV válido: " + self.caminho)

        achou_fmt = False
        while True:
            cab_chunk = f.read(8)
            if len(cab_chunk) < 8:
                raise ValueError("Chunk 'data' não encontrado")
            chunk_id = cab_chunk[0:4]
            (chunk_size,) = struct.unpack("<I", cab_chunk[4:8])

            if chunk_id == b"fmt ":
                fmt = f.read(chunk_size)
                (self.formato, self.canais, self.taxa,
                 _byte_rate, _align, self.bits) = struct.unpack("<HHIIHH", fmt[:16])
                achou_fmt = True
            elif chunk_id == b"data":
                if not achou_fmt:
                    raise ValueError("'data' antes de 'fmt '")
                self.data_inicio = f.tell()
                self.data_tamanho = chunk_size
                self.restante = chunk_size
                break
            else:
                f.seek(chunk_size, 1)  # ignora LIST, INFO, etc.

            if chunk_size & 1:         # chunks são alinhados em 2 bytes
                f.seek(1, 1)

        if self.formato != 1:
            raise ValueError("Somente WAV PCM (formato 1) é suportado")

    @property
    def duracao_s(self):
        bytes_por_seg = self.taxa * self.canais * (self.bits // 8)
        return self.data_tamanho / bytes_por_seg if bytes_por_seg else 0

    @property
    def posicao_s(self):
        bytes_por_seg = self.taxa * self.canais * (self.bits // 8)
        lidos = self.data_tamanho - self.restante
        return lidos / bytes_por_seg if bytes_por_seg else 0

    def info(self):
        return "{}: {} Hz, {} bits, {} canal(is), {:.1f} s".format(
            self.caminho, self.taxa, self.bits, self.canais, self.duracao_s)

    def ler_bloco(self, buf):
        """Lê para dentro de 'buf' (bytearray/memoryview). Retorna nº de bytes."""
        if self.restante <= 0:
            return 0
        n = self.f.readinto(buf if len(buf) <= self.restante
                            else memoryview(buf)[:self.restante])
        n = n or 0
        self.restante -= n
        return n

    def reiniciar(self):
        self.f.seek(self.data_inicio)
        self.restante = self.data_tamanho

    def buscar(self, delta_s):
        """Move a posição de leitura em delta_s segundos (negativo retrocede)."""
        frame = self.canais * (self.bits // 8)
        if frame == 0:
            return
        lidos = self.data_tamanho - self.restante
        novo = lidos + int(delta_s * self.taxa) * frame
        if novo < 0:
            novo = 0
        elif novo > self.data_tamanho:
            novo = self.data_tamanho
        novo -= novo % frame
        self.f.seek(self.data_inicio + novo)
        self.restante = self.data_tamanho - novo

    def fechar(self):
        self.f.close()


# ---------------------------------------------------------------------------
# Volume por software (o MAX98357A não tem controle de volume por I2S)
# ---------------------------------------------------------------------------
VOL_PASSO = 5                 # % por clique do encoder
volume = 50                   # 0..100 (%)


def calcula_ganho(vol):
    """Percentual -> ganho em ponto fixo (256 = 1.0). Curva quadrática."""
    return vol * vol * 256 // 10000


ganho_volume = calcula_ganho(volume)


def ajustar_volume(delta):
    global volume, ganho_volume
    if delta:
        volume = max(0, min(100, volume + delta * VOL_PASSO))
        ganho_volume = calcula_ganho(volume)


@micropython.viper
def aplicar_volume(buf, n: int, ganho: int):
    """Multiplica in-place n bytes de amostras PCM 16 bits (little-endian)."""
    p = ptr16(buf)
    for i in range(n >> 1):
        s = int(p[i])
        if s >= 32768:       # amostra com sinal
            s -= 65536
        p[i] = ((s * ganho) >> 8) & 0xFFFF


def saida_audio(dados, n, wav):
    """Envia os bytes PCM lidos do WAV ao amplificador via I2S, com volume.
    Reconfigura o I2S automaticamente se a taxa/canais do WAV forem diferentes."""
    if (wav.taxa, wav.canais, IBUF_PLAYER) != _cfg_i2s:
        abrir_i2s(wav.taxa, wav.canais, IBUF_PLAYER)
    if ganho_volume != 256:
        aplicar_volume(dados, n, ganho_volume)
    i2s_max.write(dados)


# ---------------------------------------------------------------------------
# MIDI / notas / acordes
# ---------------------------------------------------------------------------
class MIDI:
    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    CHORD_TYPES = ["Maior", "Menor", "Diminuto", "Aumentado"]
    NUM_CHORD_TYPES = len(CHORD_TYPES)

    CHORD_INTERVALS = {
        "Maior":     [0, 4, 7],
        "Menor":     [0, 3, 7],
        "Diminuto":  [0, 3, 6],
        "Aumentado": [0, 4, 8],
    }

    SCALE_INTERVALS = {
        "Maior":     [0, 2, 4, 5, 7, 9, 11, 12],
        "Menor":     [0, 2, 3, 5, 7, 8, 10, 12],
        "Diminuto":  [0, 2, 3, 5, 6, 8, 9, 11, 12],
        "Aumentado": [0, 2, 4, 6, 8, 10, 12],
    }

    CHORD_COLORS = {
        "Maior":     (0, 20, 0),
        "Menor":     (0, 0, 20),
        "Diminuto":  (20, 0, 0),
        "Aumentado": (20, 20, 0),
    }

    def __init__(self, root_base_midi=60, sample_rate=16000):
        self.root_base_midi = root_base_midi
        self.sample_rate = sample_rate
        # Afinação por nota (em cents, -50..+50), vale para todas as oitavas
        self.afinacao = [0] * 12

    @staticmethod
    def midi_to_freq(n):
        """A4 (MIDI 69) = 440 Hz, temperamento igual"""
        return 440.0 * (2 ** ((n - 69) / 12))

    def freq_afinada(self, n):
        """Frequência da nota MIDI n já com o ajuste de afinação (cents)."""
        return 440.0 * (2 ** ((n - 69) / 12 + self.afinacao[n % 12] / 1200))

    def midi_to_name(self, n):
        """Converte valor MIDI para nome com oitava (ex: 60 -> 'C4')"""
        nome = self.NOTE_NAMES[n % 12]
        oitava = (n // 12) - 1
        return nome + str(oitava)

    def nome_to_freq(self, nome):
        if len(nome) == 3:
            letra = nome[0:2]
            oitava = int(nome[2])
        else:
            letra = nome[0]
            oitava = int(nome[1])
        semitom = self.NOTE_NAMES.index(letra)
        midi = (oitava + 1) * 12 + semitom
        return self.midi_to_freq(midi)

    def obter_acorde(self, indice_raiz, tipo_acorde):
        """Retorna [(nome, freq), ...] para tônica, terça e quinta."""
        root_midi = self.root_base_midi + indice_raiz
        intervalos = self.CHORD_INTERVALS[tipo_acorde]
        return [(self.midi_to_name(root_midi + iv), self.midi_to_freq(root_midi + iv)) for iv in intervalos]

    def acorde_midis(self, indice_raiz, tipo_acorde):
        """Retorna só os números MIDI das notas do acorde."""
        root_midi = self.root_base_midi + indice_raiz
        return [root_midi + iv for iv in self.CHORD_INTERVALS[tipo_acorde]]

    def obter_escala(self, indice_raiz, tipo_acorde):
        root_midi = self.root_base_midi + indice_raiz
        intervalos = self.SCALE_INTERVALS[tipo_acorde]
        return [(self.midi_to_name(root_midi + iv), self.midi_to_freq(root_midi + iv)) for iv in intervalos]

    def wave_gen(self, frequencia, duracao_ms, volume=0.2):
        """Gera um buffer PCM 16-bit com uma senoide (mantido da versão anterior;
        o teclado agora usa o motor 'Sintese', que é bem mais rápido)."""
        num_amostras = int(self.sample_rate * (duracao_ms / 1000.0))
        if frequencia == 0:
            return bytearray(num_amostras * 2)
        amostras = array.array('h')
        amplitude = int(32767 * max(0.0, min(1.0, volume)))
        for i in range(num_amostras):
            t = i / self.sample_rate
            valor = int(amplitude * math.sin(2 * math.pi * frequencia * t))
            amostras.append(valor)
        return amostras


midi = MIDI(root_base_midi=60, sample_rate=SAMPLE_RATE)
NOTAS = MIDI.NOTE_NAMES

# Lista de acordes: 12 raízes x 4 tipos, agrupados por raiz (+ "Teclado" para voltar)
ACORDES_LISTA = [NOTAS[r] + " " + t for r in range(12) for t in MIDI.CHORD_TYPES]
MODES[4] = ACORDES_LISTA + ["Teclado"]
DURACAO_ACORDE_MS = 1500


# ---------------------------------------------------------------------------
# Motor de síntese polifônico (tabela de onda + envelope, mixagem em viper)
# ---------------------------------------------------------------------------
TAM_TAB = 1024


def _tabela(harmonicos):
    """Tabela de 1024 amostras (int16) somando harmônicos [(n, amplitude), ...].
    Usa duas passadas para não criar listas temporárias de floats."""
    gc.collect()
    w = 2 * math.pi / TAM_TAB

    # Passada 1: só descobre o pico
    pico = 0.0
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        if abs(s) > pico:
            pico = abs(s)
    k = 30000 / pico

    # Passada 2: grava direto no array de 2 KB
    tab = array.array('h', bytes(2 * TAM_TAB))
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        tab[i] = int(s * k)
    return tab


tab_seno = _tabela([(1, 1.0)])
tab_piano = _tabela([(1, 1.0), (2, 0.55), (3, 0.30), (4, 0.18), (5, 0.10), (6, 0.05)])
tab_serra = _tabela([(h, 1.0 / h) for h in range(1, 11)])   # "serra" suave (sem aliasing até B5)

# nome: (tabela, sustain/bloco, release/bloco, ataque (fração/bloco), nível Q12)
INSTR = {
    "Piano":        (tab_piano, 0.988, 0.55, 1.0, 2400),   # decai sozinho enquanto a tecla está apertada
    "Sintetizador": (tab_serra, 1.000, 0.72, 0.35, 1800),  # sustenta, ataque suave
    "Afinador":     (tab_seno,  1.000, 0.60, 0.50, 2400),  # senoide pura
}
GANHO_SINT = 2   # ganho extra do sintetizador em relação ao player


@micropython.viper
def mix_voz(acc, n: int, tab, fase: int, passo: int, a0: int, a1: int) -> int:
    """Soma n amostras de uma voz no acumulador int32 'acc'.
    fase: acumulador de 24 bits; amplitude em Q12 com rampa linear a0 -> a1."""
    pa = ptr32(acc)
    pt = ptr16(tab)
    amp = a0 << 8
    step = ((a1 - a0) << 8) // n
    for i in range(n):
        s = int(pt[fase >> 14])
        if s >= 32768:
            s -= 65536
        pa[i] = int(pa[i]) + ((s * (amp >> 8)) >> 12)
        amp += step
        fase = (fase + passo) & 0xFFFFFF
    return fase


@micropython.viper
def finalizar(acc, out, n: int, ganho: int):
    """Aplica volume, satura em 16 bits, grava em 'out' e zera o acumulador."""
    pa = ptr32(acc)
    po = ptr16(out)
    for i in range(n):
        v = (int(pa[i]) * ganho) >> 8
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        po[i] = v & 0xFFFF
        pa[i] = 0


class Sintese:
    """Gera um bloco de áudio mono 16 bits a partir da lista de notas MIDI ligadas."""

    def __init__(self, midi, bloco=256, taxa=SAMPLE_RATE):
        self.midi = midi
        self.n = bloco                      # 256 amostras = ~11,6 ms
        self.k = 16777216.0 / taxa          # 2^24 / taxa
        self.acc = array.array('i', [0] * bloco)
        self.out = bytearray(bloco * 2)
        self.vozes = {}   # midi -> [fase, amp, ligada, estava_ligada, alvo_env]

    def gerar(self, alvo, instr):
        tab, sust, rel, atk, nivel = INSTR[instr]
        vozes = self.vozes
        for v in vozes.values():
            v[3] = v[2]
            v[2] = False
        for m in alvo:
            v = vozes.get(m)
            if v is None:
                vozes[m] = [0, 0.0, True, False, nivel]
            else:
                v[2] = True
        mortos = []
        for m in vozes:
            v = vozes[m]
            amp = v[1]
            if v[2]:
                if not v[3]:
                    v[4] = nivel          # novo ataque
                v[4] *= sust
                a1 = amp + (v[4] - amp) * atk
            else:
                a1 = amp * rel
                if a1 < 8:
                    mortos.append(m)
            passo = int(self.midi.freq_afinada(m) * self.k)
            v[0] = mix_voz(self.acc, self.n, tab, v[0], passo, int(amp), int(a1))
            v[1] = a1
        for m in mortos:
            del vozes[m]
        finalizar(self.acc, self.out, self.n, ganho_volume * GANHO_SINT)
        return self.out


sintese = Sintese(midi)

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
PULO_VEL_MAX_S = 15           # s de áudio por s real, com o joystick no fundo de escala
PULO_GAP_MAX_MS = 300         # pausa maior que isso = novo gesto
PULO_PASSO_INICIAL_MS = 50    # intervalo assumido na 1ª chamada de um gesto

class Player:
    def __init__(self, arquivos, callback=saida_audio, repetir=True):
        self.arquivos = arquivos
        self.callback = callback
        self.repetir = repetir
        self.indice = 0
        self.wav = None
        self.estado = PARADO
        self.buf = bytearray(TAM_BUFFER)
        self.mv = memoryview(self.buf)
        self._t_pulo = utime.ticks_ms()

    def selecionar(self, i):
        """Troca para a faixa i (0..N-1), mesmo no meio da leitura atual."""
        if not 0 <= i < len(self.arquivos):
            return False
        self._fechar_atual()
        try:
            self.wav = WavFile(self.arquivos[i])
        except (OSError, ValueError):
            self.estado = PARADO
            return False
        if self.wav.bits != 16 or self.wav.canais not in (1, 2):
            self._fechar_atual()          # só 16 bits, mono ou estéreo
            self.estado = PARADO
            return False
        self.indice = i
        self.estado = TOCANDO
        return True

    def proximo(self):
        if not self.arquivos:
            return False
        return self.selecionar((self.indice + 1) % len(self.arquivos))

    def anterior(self):
        if not self.arquivos:
            return False
        return self.selecionar((self.indice - 1) % len(self.arquivos))

    def pausar_retomar(self):
        if self.estado == TOCANDO:
            self.estado = PAUSADO
        elif self.estado == PAUSADO:
            self.estado = TOCANDO
        elif self.estado == PARADO:
            self.selecionar(self.indice)

    def reiniciar(self):
        if self.wav:
            self.wav.reiniciar()
            self.estado = TOCANDO

    def pular(self, x, vel_max_s=PULO_VEL_MAX_S, fundo_escala=32768):
        """Avança (x > 0) ou retrocede (x < 0) a faixa atual, proporcional ao desvio."""
        if self.wav is None or self.estado == PARADO:
            return 0.0

        agora = utime.ticks_ms()
        dt_ms = utime.ticks_diff(agora, self._t_pulo)
        self._t_pulo = agora
        if dt_ms > PULO_GAP_MAX_MS:
            dt_ms = PULO_PASSO_INICIAL_MS

        frac = x / fundo_escala
        if frac > 1.0:
            frac = 1.0
        elif frac < -1.0:
            frac = -1.0

        delta = frac * vel_max_s * (dt_ms / 1000)
        self.wav.buscar(delta)
        return delta

    def parar(self):
        self._fechar_atual()
        self.estado = PARADO

    def _fechar_atual(self):
        if self.wav:
            try:
                self.wav.fechar()
            except OSError:
                pass
            self.wav = None

    def atualizar(self):
        """Lê UM bloco da faixa atual. Chame em loop."""
        if self.estado != TOCANDO or self.wav is None:
            return

        n = self.wav.ler_bloco(self.buf)
        if n:
            self.callback(self.mv[:n], n, self.wav)
            return

        # Fim da faixa
        ultima = self.indice == len(self.arquivos) - 1
        if ultima and not self.repetir:
            self.parar()
        else:
            self.proximo()


# ---------------------------------------------------------------------------
# Estado do teclado musical
# ---------------------------------------------------------------------------
instrumento = "Piano"
oitava = 4                    # 3..5 (muda com o botão do encoder)
sel_nota = 0                  # nota selecionada no Afinador (0 = C ... 11 = B)
PASSO_CENTS = 1               # passo do encoder no Afinador (cents por clique)
LIM_CENTS = 50                # afinação limitada a +-50 cents (meio semitom)
acorde_idx = 0                # acorde selecionado/tocando (índice em ACORDES_LISTA)
acorde_fim = utime.ticks_ms()
notas_tocando = []            # números MIDI soando agora (para o display)

player = None
ultima_tecla = None


def nota_midi(idx):
    return 12 * (oitava + 1) + idx


# ---------------------------------------------------------------------------
# Navegação da UI
# ---------------------------------------------------------------------------
def nav_mode(mov_x, mov_y, clicou):
    """Navega nas listas com o joystick e executa a seleção com o botão dele."""
    global mode_ui, mode_sel, instrumento, acorde_idx, acorde_fim
    itens = MODES[mode_ui]
    n = len(itens)

    if mov_y:
        mode_sel = (mode_sel + mov_y) % n
    # Na lista de acordes, o eixo X pula de raiz em raiz (4 itens)
    if mode_ui == 4 and mov_x and mode_sel < n - 1:
        mode_sel = (mode_sel + 4 * mov_x) % (n - 1)

    if not clicou:
        return

    escolhido = itens[mode_sel]

    if mode_ui == 4 and mode_sel < n - 1:      # acorde da lista: toca por 1,5 s
        acorde_idx = mode_sel
        acorde_fim = utime.ticks_add(utime.ticks_ms(), DURACAO_ACORDE_MS)
        return
    if escolhido == "Piano" or escolhido == "Sintetizador":
        instrumento = escolhido
        return

    if escolhido == "Menu":
        mode_ui = 0
    elif escolhido == "Teclado":
        mode_ui = 1
    elif escolhido == "Player":
        mode_ui = 2
    elif escolhido == "Instrumento":
        mode_ui = 3
    elif escolhido == "Acordes":
        mode_ui = 4
    else:  # "Afinador"
        mode_ui = 5
    mode_sel = 1 if mode_ui == 3 and instrumento == "Sintetizador" else 0


def entrar_modo(antigo, novo):
    """Ações ao trocar de tela."""
    global player, acorde_fim, ultima_tecla
    if antigo == 2 and player is not None:
        player.parar()
    if novo == 2:
        abrir_i2s(SAMPLE_RATE, 1, IBUF_PLAYER)
        player = Player(ARQUIVOS, repetir=REPETIR_LISTA)
        if ARQUIVOS:
            player.selecionar(0)
        ultima_tecla = None
    else:
        abrir_i2s(SAMPLE_RATE, 1, IBUF_SINT)
        if novo == 4:
            acorde_fim = utime.ticks_ms()


# ---------------------------------------------------------------------------
# Display (128x64 -> 8 linhas de texto de 8 px)
#
# Grade vertical usada em todas as telas:
#   y =  0        título (linha 0) + linha divisória em y = 9
#   y = 11 + 9*k  linhas de conteúdo (k = 0, 1, 2, ...)
#   y = 47        linha de notas tocando      (telas de teclado)
#   y = 56        última linha (status / botão "voltar")
# ---------------------------------------------------------------------------
Y_INI = 11            # primeira linha de conteúdo
Y_PASSO = 9           # espaçamento entre linhas de conteúdo
Y_NOTAS = 47          # linha das notas tocando
Y_RODAPE = 56         # última linha do display (56..63)


def texto(s, x, y):
    oled.text(s, x, y, 1)


def centro(s, y):
    oled.text(s, max(0, (OLED_W - 8 * len(s)) // 2), y, 1)


def cabecalho(titulo):
    centro(titulo, 0)
    oled.hline(0, 9, OLED_W, 1)


def item(s, y, sel):
    texto(("> " if sel else "  ") + s[:14], 2, y)


def fmt_tempo(s):
    s = int(s)
    return "{:02d}:{:02d}".format(s // 60, s % 60)


def janela(txt, t):
    """Letreiro rolante para nomes com mais de 16 caracteres."""
    if len(txt) <= 16:
        return txt
    extra = len(txt) - 16
    off = t % (extra + 4)
    if off > extra:
        off = extra
    return txt[off:off + 16]


def triangulo(x, y, h, direita):
    wd = h // 2
    meio = h // 2
    for c in range(wd):
        metade = meio * (wd - c) // wd
        xx = x + c if direita else x + wd - 1 - c
        oled.vline(xx, y + meio - metade, 2 * metade + 1, 1)


def desenha_notas(y):
    """Uma linha com o que está soando: nota + frequência (1 nota) ou a lista de notas (acorde)."""
    if not notas_tocando:
        texto("Tocando: -", 2, y)
    elif len(notas_tocando) == 1:
        m = notas_tocando[0]
        texto("{} {:.1f}Hz".format(midi.midi_to_name(m), midi.freq_afinada(m))[:16], 2, y)
    else:
        texto(" ".join(midi.midi_to_name(m) for m in notas_tocando)[:16], 2, y)


def desenha_status(y):
    texto("{} O{} V{}".format(instrumento[:5], oitava, volume), 2, y)


def desenha_player():
    cabecalho("Player")
    p = player
    if p is None or not ARQUIVOS:
        centro("Sem arquivos", 24)
        centro("WAV no SD", 34)
    else:
        nome = p.arquivos[p.indice].split("/")[-1]
        if nome.lower().endswith(".wav"):
            nome = nome[:-4]
        pos = p.wav.posicao_s if p.wav else 0
        dur = p.wav.duracao_s if p.wav else 0
        centro(janela(nome, int(pos)), 11)
        centro("{}/{} Vol:{}%".format(p.indice + 1, len(p.arquivos), volume), 20)
        centro("{} / {}".format(fmt_tempo(pos), fmt_tempo(dur)), 29)
        # Símbolos multimídia (altura 9 px): prévio | play/pause | próximo
        ys = 38
        oled.fill_rect(33, ys, 2, 9, 1)
        triangulo(36, ys, 8, False)
        if p.estado == TOCANDO:
            oled.fill_rect(60, ys, 3, 9, 1)
            oled.fill_rect(66, ys, 3, 9, 1)
        else:
            triangulo(62, ys, 8, True)
        triangulo(89, ys, 8, True)
        oled.fill_rect(93, ys, 2, 9, 1)
        # Barra de progresso
        oled.rect(8, 49, 112, 5, 1)
        if dur > 0:
            oled.fill_rect(8, 49, int(112 * min(pos / dur, 1.0)), 5, 1)
    item("Menu", Y_RODAPE, True)


def desenha_afinador():
    cabecalho("Afinador")
    ant = NOTAS[(sel_nota - 1) % 12]
    prox = NOTAS[(sel_nota + 1) % 12]
    cents = midi.afinacao[sel_nota]
    m = nota_midi(sel_nota)
    centro("{} [{}] {}".format(ant, midi.midi_to_name(m), prox), 11)
    texto("Freq:{:.2f}Hz".format(midi.freq_afinada(m)), 8, 20)
    texto("Padrao:{:.2f}Hz".format(midi.midi_to_freq(m)), 0, 29)
    texto("Ajuste:{:+d} cent".format(cents), 0, 38)
    # Medidor: centro = nota certa (Enc: afina | Joy: troca de nota)
    oled.rect(14, 47, 101, 8, 1)
    oled.vline(64, 45, 11, 1)
    oled.fill_rect(64 + cents * 50 // LIM_CENTS - 1, 49, 3, 4, 1)
    item("Teclado", Y_RODAPE, True)


def desenhar():
    oled.fill(0)
    if mode_ui == 0:
        cabecalho("RaspHarmony")
        centro("Menu Principal", 13)
        for i, nome in enumerate(MODES[0]):
            item(nome, 28 + 12 * i, i == mode_sel)

    elif mode_ui == 1:
        cabecalho("Teclado")
        for i, nome in enumerate(MODES[1]):
            item(nome, Y_INI + Y_PASSO * i, i == mode_sel)
        desenha_notas(Y_NOTAS)
        desenha_status(Y_RODAPE)

    elif mode_ui == 2:
        desenha_player()

    elif mode_ui == 3:
        cabecalho("Instrumento")
        for i, nome in enumerate(MODES[3]):
            marca = " *" if nome == instrumento else ""
            item(nome + marca, Y_INI + Y_PASSO * i, i == mode_sel)
        desenha_notas(Y_NOTAS)
        desenha_status(Y_RODAPE)

    elif mode_ui == 4:
        cabecalho("Acordes")
        itens = MODES[4]
        n = len(itens)
        ini = max(0, min(mode_sel - 1, n - 4))     # janela rolante de 4 itens
        for k in range(4):
            i = ini + k
            item(itens[i], Y_INI + Y_PASSO * k, i == mode_sel)
        if mode_sel < n - 1:
            raiz, tipo = mode_sel // 4, MIDI.CHORD_TYPES[mode_sel % 4]
            ms = midi.acorde_midis(raiz, tipo)
            texto(" ".join(midi.midi_to_name(m) for m in ms)[:16], 2, Y_NOTAS + 1)
            if acorde_ativo():
                texto("Tocando...", 2, Y_RODAPE)
            else:
                texto("Joy: tocar", 2, Y_RODAPE)

    else:
        desenha_afinador()

    oled.show()


def acorde_ativo():
    return utime.ticks_diff(acorde_fim, utime.ticks_ms()) > 0


def chave_visual():
    """Resumo do que está na tela; só redesenha quando isso muda."""
    if mode_ui == 2 and player is not None:
        pos = int(player.wav.posicao_s) if player.wav else 0
        return (2, player.indice, player.estado, pos, volume)
    return (mode_ui, mode_sel, tuple(notas_tocando), volume, instrumento, oitava,
            sel_nota, midi.afinacao[sel_nota], acorde_ativo())


# ---------------------------------------------------------------------------
# Laços de cada família de modos
# ---------------------------------------------------------------------------
def loop_player(x, delta_enc):
    global ultima_tecla
    ajustar_volume(delta_enc)

    tecla = key_notes_scan(0)             # botões multimídia (linha 4)
    if tecla != ultima_tecla:             # só age na borda (um aperto = uma ação)
        ultima_tecla = tecla
        if tecla and ARQUIVOS:
            if tecla == "Play/Stop":
                player.pausar_retomar()
            elif tecla == "Next":
                player.proximo()
            elif tecla == "Prev":
                player.anterior()
            elif tecla == "Reinicia":
                player.reiniciar()

    if ARQUIVOS and abs(x) > LIMIAR:      # joystick em X: avança/retrocede
        player.pular(x)

    if player.estado == TOCANDO:
        player.atualizar()                # lê e envia o próximo bloco
    else:
        i2s_max.write(SILENCIO)           # pausado: mantém o I2S alimentado


def loop_sintetizador(mov_x, delta_enc, clique_enc):
    """Teclado / Instrumento / Acordes / Afinador (e Menu, em silêncio)."""
    global oitava, sel_nota, notas_tocando
    alvo = []
    instr = instrumento

    if mode_ui == 5:                                  # ---- Afinador
        instr = "Afinador"
        nomes = key_notes_scan(1)
        if nomes:                                     # tecla seleciona a nota
            sel_nota = NOTAS.index(nomes[0])
        elif mov_x:                                   # joystick navega entre as notas
            sel_nota = (sel_nota + mov_x) % 12
        if delta_enc:
            c = midi.afinacao[sel_nota] + delta_enc * PASSO_CENTS
            midi.afinacao[sel_nota] = max(-LIM_CENTS, min(LIM_CENTS, c))
        if clique_enc:                                # botão do encoder zera a afinação
            midi.afinacao[sel_nota] = 0
        alvo = [nota_midi(sel_nota)]

    else:
        ajustar_volume(delta_enc)
        if mode_ui == 1 or mode_ui == 3:              # ---- Teclado / Instrumento
            if clique_enc:
                oitava = oitava + 1 if oitava < 5 else 3
            alvo = [nota_midi(NOTAS.index(nm)) for nm in key_notes_scan(1)]
        elif mode_ui == 4 and acorde_ativo():         # ---- Acordes
            alvo = midi.acorde_midis(acorde_idx // 4, MIDI.CHORD_TYPES[acorde_idx % 4])

    notas_tocando = alvo
    i2s_max.write(sintese.gerar(alvo, instr))         # sempre escreve (silêncio se vazio)


# ------------------------------------------------------------
# Loop principal
# ------------------------------------------------------------
chave_ant = None
while True:
    x, mov_x, mov_y = joystick_sense()
    modo_ant = mode_ui
    nav_mode(mov_x, mov_y, btn_joy.pressionado())
    if mode_ui != modo_ant:
        entrar_modo(modo_ant, mode_ui)

    delta_enc = enc.cliques()
    clique_enc = btn_enc.pressionado()

    if mode_ui == 2:
        loop_player(x, delta_enc)
    else:
        loop_sintetizador(mov_x, delta_enc, clique_enc)

    chave = chave_visual()
    if chave != chave_ant:
        chave_ant = chave
        desenhar()