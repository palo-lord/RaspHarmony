# ============================================================
# RaspHarmony - Sistema Embarcado Sintetizador e Reprodutor de Áudio
# ============================================================
# Nome: Paulo Sergio Gonçalves Júnior RA: 218474
# Nome: Vinicius Pedrillo de Souza RA: 258667
# ============================================================
# VERSÃO MONOLÍTICA (arquivo único) - gerada a partir da versão
# modular (protoboard_version/modular).
# Dependências externas (copiar para o Pico): sh1106.py, sdcard.py
#
# Seções, na ordem:
#   config, Encoder, Botao, Joystick, Teclado, armazenamento (SD),
#   WavFile, SaidaAudio, MIDI, Sintese, Player, Estado, Tela, Aplicacao
# ============================================================
from machine import Pin, ADC, I2C, SPI, I2S, disable_irq, enable_irq
from sh1106 import SH1106_I2C
import utime
import math
import array
import gc
import random
import os
import struct
import micropython
import sdcard

micropython.alloc_emergency_exception_buf(100)  # permite ver erros dentro de IRQ



# ==========================================================
# [config]
# ==========================================================
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
INVERTE_X = True    # troque para True se o joystick navegar ao contrário
INVERTE_Y = True
LIMIAR = 12000       # sensibilidade para detectar movimento

# Cartão SD (SPI)
SD_MOUNT = "/sd"
SD_SCK, SD_MOSI, SD_MISO, SD_CS = 18, 19, 16, 17
TAM_BUFFER = 8192    # bytes lidos por vez do SD (múltiplo de 512 é ideal), 93ms
REPETIR_LISTA = True

# Estados do Player
PARADO, TOCANDO, PAUSADO = 0, 1, 2

# Áudio / I2S
SAMPLE_RATE = 44100
IBUF_SINT = 4096     # ~46.5 ms de latência no teclado
IBUF_PLAYER = 32768   # ~372 ms de folga (mono); custa 16 KB a mais de RAM

# Volume
VOL_PASSO = 2        # % por clique do encoder
VOLUME_INICIAL = 30

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


# ==========================================================
# [encoder]
# ==========================================================
# ============================================================
# encoder.py - Encoder rotativo em quadratura
# ============================================================

# Tabela de decodificação em quadratura.
# Índice = (estado_anterior << 2) | estado_novo, com estado = (A << 1) | B.
_TAB_ENC = (0, 1, -1, 0,
            -1, 0, 0, 1,
            1, 0, 0, -1,
            0, -1, 1, 0)


class Encoder:
    """Encoder rotativo em quadratura. A interrupção só acumula passos;
    o resto do programa lê com cliques(), sem nunca mexer em SD/I2S/OLED na IRQ."""

    def __init__(self, pino_a, pino_b, passos_por_clique=2):
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
        c = -self.contagem
        n = c // self.ppc if c >= 0 else -((-c) // self.ppc)
        self.contagem = c - n * self.ppc   # guarda o resto de um clique incompleto
        enable_irq(st)
        return n


# ==========================================================
# [botao]
# ==========================================================
# ============================================================
# botao.py - Botão com detecção de borda e debounce sem sleep
# ============================================================


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


# ==========================================================
# [joystick]
# ==========================================================
# ============================================================
# joystick.py - Joystick analógico com botão
# ============================================================



class Joystick:
    def __init__(self, pin_x, pin_y, pin_sw, limiar=12000,
                 inverte_x=True, inverte_y=True):
        self.sw = Pin(pin_sw, Pin.IN, Pin.PULL_UP)
        self.adc_x = ADC(Pin(pin_x))
        self.adc_y = ADC(Pin(pin_y))
        self.botao = Botao(self.sw)
        self.limiar = limiar
        self.inverte_x = inverte_x
        self.inverte_y = inverte_y
        self.neutra_x = True
        self.neutra_y = True

        utime.sleep_ms(100)  # calibração do centro do joystick
        self.centro_x = self.adc_x.read_u16()
        self.centro_y = self.adc_y.read_u16()

    def ler(self):
        """Retorna (x, movimento_x, movimento_y).
        x = desvio analógico em X (para o 'pular' do Player);
        movimento_x/y = -1, 0 ou +1, UM evento por empurrão (com histerese)."""
        x = self.centro_x - self.adc_x.read_u16()
        y = self.centro_y - self.adc_y.read_u16()
        if self.inverte_x:
            x = -x
        if self.inverte_y:
            y = -y

        lim = self.limiar
        movimento_x = 0
        movimento_y = 0

        if self.neutra_x:
            if x > lim:
                movimento_x = 1
                self.neutra_x = False
            elif x < -lim:
                movimento_x = -1
                self.neutra_x = False
        elif abs(x) < lim // 3:
            self.neutra_x = True

        if self.neutra_y:
            if y > lim:
                movimento_y = 1
                self.neutra_y = False
            elif y < -lim:
                movimento_y = -1
                self.neutra_y = False
        elif abs(y) < lim // 3:
            self.neutra_y = True

        return (x, movimento_x, movimento_y)

    def clicou(self):
        return self.botao.pressionado()


# ==========================================================
# [teclado]
# ==========================================================
# ============================================================
# teclado.py - Teclado matricial 4x4
# ============================================================

SETTLE_US = 20   # tempo para a coluna estabilizar depois de ativar a linha


class Teclado:
    """Matriz 4x4 ativa em nível baixo: colunas com PULL_UP, tecla apertada = 0.

    As linhas ficam em ALTA IMPEDÂNCIA (entrada) em repouso e só a linha que está
    sendo varrida é levada a 0 V. Assim uma tecla fechada em outra linha (por exemplo
    as multimídia) não puxa nenhuma coluna para baixo, e duas teclas apertadas na
    mesma coluna (C e E, por exemplo) não colocam uma linha em 0 contra outra em 1."""

    def __init__(self, row_pins, col_pins, key_notes):
        self.key_notes = key_notes
        self.rows = [Pin(p, Pin.IN) for p in row_pins]
        self.cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in col_pins]

    def _colunas_pressionadas(self, r_idx):
        """Índices das colunas com tecla apertada na linha r_idx."""
        row = self.rows[r_idx]
        row.init(Pin.OUT, value=0)
        utime.sleep_us(SETTLE_US)
        achadas = [c for c, col in enumerate(self.cols) if col.value() == 0]
        row.init(Pin.IN)               # volta para alta impedância
        return achadas

    def scan(self, flag_teclado):
        """flag_teclado=True: varre as 3 primeiras linhas e retorna a lista de notas.
        flag_teclado=False: varre a última linha (multimídia) e retorna a tecla ou None."""
        if flag_teclado:
            lista = []
            for r_idx in range(3):
                for c_idx in self._colunas_pressionadas(r_idx):
                    lista.append(self.key_notes[r_idx][c_idx])
            return lista

        colunas = self._colunas_pressionadas(3)
        if colunas:
            return self.key_notes[3][colunas[0]]
        return None


# ==========================================================
# [armazenamento]
# ==========================================================
# ============================================================
# armazenamento.py - Cartão SD (SPI): montagem e lista de WAVs
# ============================================================


def montar_sd(sck, mosi, miso, cs_pin, ponto_montagem):
    """Monta o SD e retorna a lista de caminhos .wav.
    Se o cartão não estiver presente, retorna lista vazia (o Teclado continua funcionando)."""
    spi = SPI(0, baudrate=8000000, polarity=0, phase=0,
              sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
    cs = Pin(cs_pin, Pin.OUT)
    cs.value(1)  # Desativa o dispositivo inicialmente

    try:
        sd = sdcard.SDCard(spi, cs)
        try:
            os.mount(sd, ponto_montagem)
        except OSError:
            pass  # já montado
        return [ponto_montagem + "/" + nome
                for nome in sorted(os.listdir(ponto_montagem))
                if nome.lower().endswith(".wav")]
    except Exception as e:
        print("SD indisponivel:", e)
        return []


# ==========================================================
# [wavfile]
# ==========================================================
# ============================================================
# wavfile.py - Leitura de arquivos WAV PCM
# ============================================================


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


# ==========================================================
# [audio]
# ==========================================================
# ============================================================
# audio.py - Saída de áudio I2S (MAX98357A) e volume por software
# ============================================================


SILENCIO = bytearray(512)
GANHO_UNIT = 4096

def calcula_ganho(vol):
    """Percentual -> ganho em ponto fixo (256 = 1.0). Curva quadrática."""
    g = vol * vol * GANHO_UNIT // 10000
    if vol > 0 and g < 1:
        g = 1
    return g

@micropython.viper
def aplicar_volume(buf, n: int, ganho: int):
    """Multiplica in-place n bytes de amostras PCM 16 bits (little-endian)."""
    p = ptr16(buf)
    for i in range(n >> 1):
        s = int(p[i])
        if s >= 32768:       # amostra com sinal
            s -= 65536
        p[i] = ((s * ganho) >> 12) & 0xFFFF


class SaidaAudio:
    """Gerencia o I2S e o volume (o MAX98357A não tem controle de volume por I2S)."""

    def __init__(self):
        self.i2s = None
        self._cfg = None
        self.volume = VOLUME_INICIAL          # 0..100 (%)
        self.ganho = calcula_ganho(self.volume)
        self.mudo = False
        
    def _atualiza_ganho(self):
        self.ganho = 0 if self.mudo else calcula_ganho(self.volume)

    def alternar_mudo(self):
        self.mudo = not self.mudo
        self._atualiza_ganho()

    def desmutar(self):
        self.mudo = False
        self._atualiza_ganho()

    def abrir(self, taxa, canais, ibuf):
        """(Re)cria o I2S só se a configuração mudou."""
        cfg = (taxa, canais, ibuf)
        if cfg == self._cfg:
            return
        if self.i2s is not None:
            self.i2s.deinit()
        self.i2s = I2S(0,
            sck=Pin(SCK_PIN),
            ws=Pin(WS_PIN),
            sd=Pin(SD_PIN),
            mode=I2S.TX,
            rate=taxa,
            bits=16,
            format=I2S.STEREO if canais == 2 else I2S.MONO,
            ibuf=ibuf)
        self._cfg = cfg

    def ajustar_volume(self, delta):
        if delta:
            self.volume = max(0, min(100, self.volume + delta * VOL_PASSO))            
            self.mudo = False
            
            self._atualiza_ganho()

    def escrever(self, dados):
        self.i2s.write(dados)

    def saida_wav(self, dados, n, wav):
        """Callback do Player: envia PCM do WAV ao amplificador, com volume.
        Reconfigura o I2S automaticamente se taxa/canais do WAV forem diferentes."""
        if (wav.taxa, wav.canais, IBUF_PLAYER) != self._cfg:
            self.abrir(wav.taxa, wav.canais, IBUF_PLAYER)
        if self.ganho != GANHO_UNIT:
            aplicar_volume(dados, n, self.ganho)
        self.i2s.write(dados)


# ==========================================================
# [midi]
# ==========================================================
# ============================================================
# midi.py - Notas, frequências, acordes e escalas
# ============================================================



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

    def __init__(self, root_base_midi=60, sample_rate=44100):
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
        o teclado usa o motor 'Sintese', que é bem mais rápido)."""
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


NOTAS = MIDI.NOTE_NAMES

# Lista de acordes: 12 raízes x 4 tipos, agrupados por raiz
ACORDES_LISTA = [NOTAS[r] + " " + t for r in range(12) for t in MIDI.CHORD_TYPES]

midi = MIDI(root_base_midi=60, sample_rate=SAMPLE_RATE)


# ==========================================================
# [sintese]
# ==========================================================
# ============================================================
# sintese.py - Motor de síntese polifônico (tabela de onda + envelope)
# ============================================================


TAM_TAB = 1024


def _tabela(harmonicos, alvo_rms=None):
    """Tabela de 1024 amostras (int16) somando harmônicos [(n, amplitude), ...].
    Usa duas passadas para não criar listas temporárias de floats.
    alvo_rms=None: normaliza o PICO em 30000 (comportamento original).
    alvo_rms=N:    normaliza a energia (RMS) em N, limitando o pico a 32000,
                   para tabelas diferentes terem o mesmo volume percebido."""
    gc.collect()
    w = 2 * math.pi / TAM_TAB

    # Passada 1: descobre o pico (e a energia)
    pico = 0.0
    soma2 = 0.0
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        if abs(s) > pico:
            pico = abs(s)
        soma2 += s * s
    if alvo_rms is None:
        k = 30000 / pico
    else:
        k = alvo_rms / math.sqrt(soma2 / TAM_TAB)
        if pico * k > 32000:
            k = 32000 / pico

    # Passada 2: grava direto no array de 2 KB
    tab = array.array('h', bytes(2 * TAM_TAB))
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        tab[i] = int(s * k)
    return tab


def _sem_sinal(tab):
    """[LAÇO DUPLO] Cópia da tabela em 'H' com offset +32768 (0..65535).
    A interpolação linear funciona igual nesse domínio, e o laço viper deixa de
    precisar dos dois 'if' de correção de sinal por amostra."""
    u = array.array('H', bytes(2 * TAM_TAB))
    for i in range(TAM_TAB):
        u[i] = tab[i] + 32768
    return u


tab_seno = _tabela([(1, 1.0)])
RMS_PIANO = 14400   # [PIANO 2] mesmo RMS em todas as tabelas do piano
tab_piano = _tabela([(1, 1.0), (2, 0.55), (3, 0.30), (4, 0.18), (5, 0.10), (6, 0.05)], RMS_PIANO)
tab_serra = _tabela([(h, 1.0 / h) for h in range(1, 11)])   # "serra" suave

# ---- [PIANO 2 e 5] tabelas extras do piano --------------------------------
# tab_piano (acima) passa a ser a tabela "média" (oitava 4).
# Graves: mais harmônicos. Agudos: poucos (evita som estridente/aliasing).
tab_piano_grave = _tabela([(1, 1.0), (2, 0.70), (3, 0.50), (4, 0.35), (5, 0.25),
                           (6, 0.18), (7, 0.12), (8, 0.08), (9, 0.05), (10, 0.03)], RMS_PIANO)
tab_piano_agudo = _tabela([(1, 1.0), (2, 0.35), (3, 0.12), (4, 0.04)], RMS_PIANO)
# Tabela "escura": a nota vai migrando da tabela rica para esta enquanto decai.
tab_escura = _tabela([(1, 1.0), (2, 0.25)], RMS_PIANO)

# [LAÇO DUPLO] versões sem sinal (offset +32768) usadas só pelo piano.
# Índice = registro: 0 = oitava 3 (e abaixo), 1 = oitava 4, 2 e 3 = oitava 5 (e acima)
U_GRAVE = _sem_sinal(tab_piano_grave)
U_MEDIA = _sem_sinal(tab_piano)
U_AGUDO = _sem_sinal(tab_piano_agudo)
U_ESCURA = _sem_sinal(tab_escura)
TABS_RICAS_U = (U_GRAVE, U_MEDIA, U_AGUDO, U_AGUDO)

# ---- [PIANO 3] tabela de ruído para a "martelada" -------------------------
tab_ruido = array.array('h', bytes(2 * TAM_TAB))
for _i in range(TAM_TAB):
    tab_ruido[_i] = random.getrandbits(15) - 16384

# nome: (tabela, sustain/bloco, release/bloco, ataque (fração/bloco), nível Q12)
# Obs.: o "Piano" usa o caminho próprio de gerar() (parâmetros PIANO abaixo);
# a linha dele aqui só mantém o formato da tabela.
# Todos os valores "por bloco" desta tabela e dos parâmetros do piano abaixo são
# referidos a um bloco de 256 amostras; Sintese os escala para o bloco real.
INSTR = {
    "Piano":        (tab_piano, 0.988, 0.55, 1.0, 2400),
    "Sintetizador": (tab_serra, 1.000, 0.72, 0.35, 1800),  # sustenta, ataque suave
    "Afinador":     (tab_seno,  1.000, 0.60, 0.50, 2400),  # senoide pura
}
GANHO_SINT = 2   # ganho extra do sintetizador em relação ao player
BLOCO_REF = 256  # tamanho de bloco ao qual as constantes por bloco se referem

# ---- Parâmetros do piano (referidos a 1 bloco de 256 amostras = 5,8 ms a 44,1 kHz) ----
# [PIANO 1] decaimento em duas fases, por registro
F_RAPIDO = 0.974                                  # fase rápida: tau ~0,22 s
FATOR_LENTO = (0.9982, 0.9972, 0.9958, 0.9936)    # fase lenta: C3 3,2 s ... C6 0,9 s
PESO_RAPIDO = 0.6                                 # peso da fase rápida na amplitude
REL_PIANO = (0.70, 0.65, 0.60, 0.55)              # release por registro (grave dura mais)
# [PIANO 2] brilho que decai
F_BRILHO = 0.968                                  # tau ~0,18 s
PISO_BRILHO = 0.25                                # nunca vira senoide pura
# [PIANO 3] ataque e martelada
NIVEL_PIANO = 1700                                # nível Q12 por voz (antes 2400)
ATAQUE_INICIAL = 0.9                              # fração do nível já no 1º bloco
RUIDO_NIVEL = 0.10                                # martelada = 10% do nível
RUIDO_FATOR = 0.6                                 # cai ~17 ms
PASSO_RUIDO = 10368889                            # ~0,618 * 2^24 (não repete padrão)
# [PIANO 4] duas cordas
DESAFINA = 1.0015                                 # ~2,5 cents
CORDA2 = 0.35                                     # fatia da 2ª corda (desigual: o batimento
                                                  # vira ondulação, sem "apagar" a nota)
# [PIANO 6] polifonia
MAX_VOZES = 4                                     # [LAÇO DUPLO] antes 6 (limita o pior caso de CPU)


@micropython.viper
def mix_voz(acc, n: int, tab, fase: int, passo: int, a0: int, a1: int) -> int:
    """Soma n amostras de uma voz no acumulador int32 'acc' (tabela com sinal, 'h').
    fase: acumulador de 24 bits; amplitude em Q12 com rampa linear a0 -> a1.
    [PIANO 5] leitura da tabela com interpolação linear (menos granulação).
    Usada pelos instrumentos simples e pela martelada do piano."""
    pa = ptr32(acc)
    pt = ptr16(tab)
    amp = a0 << 8
    step = ((a1 - a0) << 8) // n
    for i in range(n):
        k = fase >> 14                    # índice (10 bits)
        fr = (fase >> 6) & 255            # fração entre amostras (8 bits)
        s0 = int(pt[k])
        s1 = int(pt[(k + 1) & 1023])
        if s0 >= 32768:
            s0 -= 65536
        if s1 >= 32768:
            s1 -= 65536
        s = s0 + (((s1 - s0) * fr) >> 8)
        pa[i] = int(pa[i]) + ((s * (amp >> 8)) >> 12)
        amp += step
        fase = (fase + passo) & 0xFFFFFF
    return fase


@micropython.viper
def mix_dupla(acc, n: int, tabA, tabB, fase: int, passo: int, par) -> int:
    """[LAÇO DUPLO] Uma corda do piano: lê as tabelas A (rica) e B (escura) na MESMA
    fase, num único laço. Troca 2 chamadas de mix_voz por 1 e calcula índice,
    fração e fase uma vez só.
    tabA/tabB: tabelas SEM sinal ('H', offset +32768), ver _sem_sinal().
    par: array('i') de 4 posições = [a0A, a1A, a0B, a1B] (amplitudes Q12 inicial/final
         de cada tabela; rampa linear no bloco). Vai num array para manter 7 argumentos,
         como o mix_voz.
    Retorna a nova fase (24 bits)."""
    pa = ptr32(acc)
    pA = ptr16(tabA)
    pB = ptr16(tabB)
    pp = ptr32(par)
    a0 = int(pp[0])
    a1 = int(pp[1])
    b0 = int(pp[2])
    b1 = int(pp[3])
    ampA = a0 << 8
    ampB = b0 << 8
    stA = ((a1 - a0) << 8) // n
    stB = ((b1 - b0) << 8) // n
    for i in range(n):
        k = fase >> 14
        fr = (fase >> 6) & 255
        k1 = (k + 1) & 1023
        x0 = int(pA[k])
        x1 = int(pA[k1])
        y0 = int(pB[k])
        y1 = int(pB[k1])
        sA = x0 + (((x1 - x0) * fr) >> 8) - 32768
        sB = y0 + (((y1 - y0) * fr) >> 8) - 32768
        pa[i] = int(pa[i]) + ((sA * (ampA >> 8) + sB * (ampB >> 8)) >> 12)
        ampA += stA
        ampB += stB
        fase = (fase + passo) & 0xFFFFFF
    return fase


@micropython.viper
def finalizar(acc, out, n: int, ganho: int):
    """Aplica volume, satura em 16 bits, grava em 'out' e zera o acumulador."""
    pa = ptr32(acc)
    po = ptr16(out)
    for i in range(n):
        v = ((int(pa[i]) >> 2) * ganho) >> 10
        # [PIANO 6] joelho suave: acima de 16384 a inclinação cai para 1/8,
        # em vez de cortar seco (acordes e volume alto distorciam).
        if v > 16384:
            v = 16384 + ((v - 16384) >> 3)
        elif v < -16384:
            v = -16384 + ((v + 16384) >> 3)
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        po[i] = v & 0xFFFF
        pa[i] = 0


class Sintese:
    """Gera um bloco de áudio mono 16 bits a partir da lista de notas MIDI ligadas.

    bloco: amostras por bloco (256 = 5,8 ms, 512 = 11,6 ms a 44,1 kHz). As constantes
    de envelope são dadas "por bloco de 256" e aqui são elevadas a (bloco/256), então o
    tempo de decaimento/release/ataque em segundos NÃO muda com o tamanho do bloco."""

    def __init__(self, midi, bloco=256, taxa=SAMPLE_RATE):
        self.midi = midi
        self.n = bloco
        self.k = 16777216.0 / taxa          # 2^24 / taxa
        self.acc = array.array('i', [0] * bloco)
        self.out = bytearray(bloco * 2)
        self.par = array.array('i', [0, 0, 0, 0])   # amplitudes passadas ao mix_dupla

        e = bloco / BLOCO_REF
        # piano
        self.f_rapido = F_RAPIDO ** e
        self.f_lento = tuple(f ** e for f in FATOR_LENTO)
        self.f_brilho = F_BRILHO ** e
        self.rel_piano = tuple(r ** e for r in REL_PIANO)
        self.ruido_fator = RUIDO_FATOR ** e
        # demais instrumentos: sustain e release multiplicam por bloco; o ataque é uma
        # fração do caminho percorrido por bloco -> 1 - (1 - atk)^e
        self.instr = {}
        for nome in INSTR:
            tab, sust, rel, atk, nivel = INSTR[nome]
            self.instr[nome] = (tab, sust ** e, rel ** e, 1.0 - (1.0 - atk) ** e, nivel)

        # midi -> [fase, amp, ligada, estava_ligada, alvo_env,          (todos os instrumentos)
        #          a_rapida, a_lenta, exc_brilho, fase2, ruido]         (só o piano usa)
        self.vozes = {}

    def gerar(self, alvo, instr, ganho_volume):
        tab, sust, rel, atk, nivel = self.instr[instr]
        piano = instr == "Piano"
        n = self.n
        acc = self.acc
        par = self.par
        vozes = self.vozes
        if len(alvo) > MAX_VOZES:           # [PIANO 6] limite de polifonia
            alvo = alvo[:MAX_VOZES]
        for v in vozes.values():
            v[3] = v[2]
            v[2] = False
        for m in alvo:
            v = vozes.get(m)
            if v is None:
                vozes[m] = [0, 0.0, True, False, nivel, 0.0, 0.0, 1.0, 0, 0.0]
            else:
                v[2] = True
        mortos = []
        for m in vozes:
            v = vozes[m]
            amp = v[1]
            passo = int(self.midi.freq_afinada(m) * self.k)

            if piano:
                # registro: 0 = oitava 3 ... 3 = oitava 6
                reg = (m - 48) // 12
                if reg < 0:
                    reg = 0
                elif reg > 3:
                    reg = 3

                if v[2]:                                    # tecla apertada
                    if not v[3]:                            # novo ataque
                        v[5] = NIVEL_PIANO                  # [PIANO 1] fase rápida
                        v[6] = NIVEL_PIANO                  # [PIANO 1] fase lenta
                        v[7] = 1.0                          # [PIANO 2] brilho máximo
                        v[9] = NIVEL_PIANO * RUIDO_NIVEL    # [PIANO 3] martelada
                        if amp == 0.0:                      # voz nova: ataque imediato
                            amp = NIVEL_PIANO * ATAQUE_INICIAL
                    w0 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                    v[5] *= self.f_rapido                   # [PIANO 1]
                    v[6] *= self.f_lento[reg]               # [PIANO 1]
                    v[7] *= self.f_brilho                   # [PIANO 2]
                    a1 = PESO_RAPIDO * v[5] + (1.0 - PESO_RAPIDO) * v[6]
                    w1 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                else:                                       # tecla solta: release
                    a1 = amp * self.rel_piano[reg]          # [PIANO 1]
                    w0 = w1 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                    if a1 < 8:
                        mortos.append(m)

                rica = TABS_RICAS_U[reg]                    # [PIANO 5] tabela por registro
                passo2 = int(passo * DESAFINA)              # [PIANO 4] 2ª corda
                h0 = amp * (1.0 - CORDA2)                   # corda 1 (65%)
                h1 = a1 * (1.0 - CORDA2)
                g0 = amp * CORDA2                           # corda 2 (35%)
                g1 = a1 * CORDA2
                f1 = v[0]
                f2 = v[8]
                # [PIANO 2 + 4] 2 cordas, cada uma = tabela rica + tabela escura num só laço
                par[0] = int(h0 * w0)
                par[1] = int(h1 * w1)
                par[2] = int(h0 * (1.0 - w0))
                par[3] = int(h1 * (1.0 - w1))
                v[0] = mix_dupla(acc, n, rica, U_ESCURA, f1, passo, par)
                par[0] = int(g0 * w0)
                par[1] = int(g1 * w1)
                par[2] = int(g0 * (1.0 - w0))
                par[3] = int(g1 * (1.0 - w1))
                v[8] = mix_dupla(acc, n, rica, U_ESCURA, f2, passo2, par)
                if v[9] > 8:                                # [PIANO 3] martelada
                    rf = self.ruido_fator
                    mix_voz(acc, n, tab_ruido, f1, PASSO_RUIDO,
                            int(v[9]), int(v[9] * rf))
                    v[9] *= rf
                v[1] = a1

            else:
                if v[2]:
                    if not v[3]:
                        v[4] = nivel          # novo ataque
                    v[4] *= sust
                    a1 = amp + (v[4] - amp) * atk
                else:
                    a1 = amp * rel
                    if a1 < 8:
                        mortos.append(m)
                v[0] = mix_voz(acc, n, tab, v[0], passo, int(amp), int(a1))
                v[1] = a1
        for m in mortos:
            del vozes[m]
        finalizar(acc, self.out, n, ganho_volume * GANHO_SINT)
        return self.out


# ==========================================================
# [player]
# ==========================================================
# ============================================================
# player.py - Reprodutor de faixas WAV
# ============================================================


PULO_VEL_MAX_S = 15           # s de áudio por s real, com o joystick no fundo de escala
PULO_GAP_MAX_MS = 300         # pausa maior que isso = novo gesto
PULO_PASSO_INICIAL_MS = 50    # intervalo assumido na 1ª chamada de um gesto


class Player:
    def __init__(self, arquivos, callback, repetir=True):
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


# ==========================================================
# [estado]
# ==========================================================
# ============================================================
# estado.py - Estado global da aplicação e navegação de menus
# ============================================================


# A lista de acordes depende do módulo midi, então é montada aqui
MODES[4] = ACORDES_LISTA + ["Teclado"]


class Estado:
    def __init__(self):
        self.mode_ui = 0              # 0 = Menu principal
        self.mode_sel = 0
        self.instrumento = "Piano"
        self.oitava = 4               # 3..5 (muda com o botão do encoder)
        self.sel_nota = 0             # nota selecionada no Afinador (0 = C ... 11 = B)
        self.acorde_idx = 0           # acorde selecionado/tocando
        self.acorde_fim = utime.ticks_ms()
        self.notas_tocando = []       # números MIDI soando agora (para o display)
        self.player = None
        self.ultima_tecla = None

    def nota_midi(self, idx):
        return 12 * (self.oitava + 1) + idx

    def acorde_ativo(self):
        return utime.ticks_diff(self.acorde_fim, utime.ticks_ms()) > 0

    def nav_mode(self, mov_x, mov_y, clicou):
        """Navega nas listas com o joystick e executa a seleção com o botão dele."""
        itens = MODES[self.mode_ui]
        n = len(itens)

        if mov_y:
            self.mode_sel = (self.mode_sel + mov_y) % n
        # Na lista de acordes, o eixo X pula de raiz em raiz (4 itens)
        if self.mode_ui == 4 and mov_x and self.mode_sel < n - 1:
            self.mode_sel = (self.mode_sel + 4 * mov_x) % (n - 1)

        if not clicou:
            return

        escolhido = itens[self.mode_sel]

        if self.mode_ui == 4 and self.mode_sel < n - 1:   # acorde: toca por 1,5 s
            self.acorde_idx = self.mode_sel
            self.acorde_fim = utime.ticks_add(utime.ticks_ms(), DURACAO_ACORDE_MS)
            return
        if escolhido == "Piano" or escolhido == "Sintetizador":
            self.instrumento = escolhido
            return

        if escolhido == "Menu":
            self.mode_ui = 0
        elif escolhido == "Teclado":
            self.mode_ui = 1
        elif escolhido == "Player":
            self.mode_ui = 2
        elif escolhido == "Instrumento":
            self.mode_ui = 3
        elif escolhido == "Acordes":
            self.mode_ui = 4
        else:  # "Afinador"
            self.mode_ui = 5
        self.mode_sel = 1 if self.mode_ui == 3 and self.instrumento == "Sintetizador" else 0


# ==========================================================
# [ui]
# ==========================================================
# ============================================================
# ui.py - Interface gráfica no display OLED (128x64)
#
# Grade vertical usada em todas as telas:
#   y =  0        título (linha 0) + linha divisória em y = 9
#   y = 11 + 9*k  linhas de conteúdo (k = 0, 1, 2, ...)
#   y = 47        linha de notas tocando      (telas de teclado)
#   y = 56        última linha (status / botão "voltar")
# ============================================================


class Tela:
    def __init__(self, oled, estado, midi, audio, arquivos):
        self.oled = oled
        self.e = estado
        self.midi = midi
        self.audio = audio
        self.arquivos = arquivos

    # ---------- primitivas ----------
    def texto(self, s, x, y):
        self.oled.text(s, x, y, 1)

    def centro(self, s, y):
        self.oled.text(s, max(0, (OLED_W - 8 * len(s)) // 2), y, 1)

    def cabecalho(self, titulo):
        self.centro(titulo, 0)
        self.oled.hline(0, 9, OLED_W, 1)

    def item(self, s, y, sel):
        self.texto(("> " if sel else "  ") + s[:14], 2, y)

    @staticmethod
    def fmt_tempo(s):
        s = int(s)
        return "{:02d}:{:02d}".format(s // 60, s % 60)

    @staticmethod
    def janela(txt, t):
        """Letreiro rolante para nomes com mais de 16 caracteres."""
        if len(txt) <= 16:
            return txt
        extra = len(txt) - 16
        off = t % (extra + 4)
        if off > extra:
            off = extra
        return txt[off:off + 16]

    def triangulo(self, x, y, h, direita):
        wd = h // 2
        meio = h // 2
        for c in range(wd):
            metade = meio * (wd - c) // wd
            xx = x + c if direita else x + wd - 1 - c
            self.oled.vline(xx, y + meio - metade, 2 * metade + 1, 1)

    # ---------- componentes ----------
    def desenha_notas(self, y):
        """Uma linha com o que está soando: nota + frequência (1 nota) ou a lista de notas."""
        notas = self.e.notas_tocando
        midi = self.midi
        if not notas:
            self.texto("Tocando: -", 2, y)
        elif len(notas) == 1:
            m = notas[0]
            self.texto("{} {:.1f}Hz".format(midi.midi_to_name(m), midi.freq_afinada(m))[:16], 2, y)
        else:
            self.texto(" ".join(midi.midi_to_name(m) for m in notas)[:16], 2, y)

    def desenha_status(self, y):
        self.texto("{} O{} V{}".format(self.e.instrumento[:5], self.e.oitava, self.audio.volume), 2, y)

    # ---------- telas ----------
    def desenha_player(self):
        oled = self.oled
        p = self.e.player
        self.cabecalho("Player")
        if p is None or not self.arquivos:
            self.centro("Sem arquivos", 24)
            self.centro("WAV no SD", 34)
        else:
            nome = p.arquivos[p.indice].split("/")[-1]
            if nome.lower().endswith(".wav"):
                nome = nome[:-4]
            pos = p.wav.posicao_s if p.wav else 0
            dur = p.wav.duracao_s if p.wav else 0
            self.centro(self.janela(nome, int(pos)), 11)
            if self.audio.mudo: self.centro("{}/{} Vol:MUDO".format(p.indice + 1, len(p.arquivos)), 20)
            else: self.centro("{}/{} Vol:{}%".format(p.indice + 1, len(p.arquivos), self.audio.volume), 20)
            self.centro("{} / {}".format(self.fmt_tempo(pos), self.fmt_tempo(dur)), 29)
            # Símbolos multimídia (altura 9 px): prévio | play/pause | próximo
            ys = 38
            oled.fill_rect(33, ys, 2, 9, 1)
            self.triangulo(36, ys, 8, False)
            if p.estado == TOCANDO:
                oled.fill_rect(60, ys, 3, 9, 1)
                oled.fill_rect(66, ys, 3, 9, 1)
            else:
                self.triangulo(62, ys, 8, True)
            self.triangulo(89, ys, 8, True)
            oled.fill_rect(93, ys, 2, 9, 1)
            # Barra de progresso
            oled.rect(8, 49, 112, 5, 1)
            if dur > 0:
                oled.fill_rect(8, 49, int(112 * min(pos / dur, 1.0)), 5, 1)
        self.item("Menu", Y_RODAPE, True)

    def desenha_afinador(self):
        oled = self.oled
        midi = self.midi
        sel = self.e.sel_nota
        self.cabecalho("Afinador")
        ant = NOTAS[(sel - 1) % 12]
        prox = NOTAS[(sel + 1) % 12]
        cents = midi.afinacao[sel]
        m = self.e.nota_midi(sel)
        self.centro("{} [{}] {}".format(ant, midi.midi_to_name(m), prox), 11)
        self.texto("Freq:{:.2f}Hz".format(midi.freq_afinada(m)), 8, 20)
        self.texto("Padrao:{:.2f}Hz".format(midi.midi_to_freq(m)), 0, 29)
        self.texto("Ajuste:{:+d} cent".format(cents), 0, 38)
        # Medidor: centro = nota certa (Enc: afina | Joy: troca de nota)
        oled.rect(14, 47, 101, 8, 1)
        oled.vline(64, 45, 11, 1)
        oled.fill_rect(64 + cents * 50 // LIM_CENTS - 1, 49, 3, 4, 1)
        self.item("Teclado", Y_RODAPE, True)

    def desenhar(self):
        e = self.e
        midi = self.midi
        self.oled.fill(0)
        if e.mode_ui == 0:
            self.cabecalho("RaspHarmony")
            self.centro("Menu Principal", 13)
            for i, nome in enumerate(MODES[0]):
                self.item(nome, 28 + 12 * i, i == e.mode_sel)

        elif e.mode_ui == 1:
            self.cabecalho("Teclado")
            for i, nome in enumerate(MODES[1]):
                self.item(nome, Y_INI + Y_PASSO * i, i == e.mode_sel)
            self.desenha_notas(Y_NOTAS)
            self.desenha_status(Y_RODAPE)

        elif e.mode_ui == 2:
            self.desenha_player()

        elif e.mode_ui == 3:
            self.cabecalho("Instrumento")
            for i, nome in enumerate(MODES[3]):
                marca = " *" if nome == e.instrumento else ""
                self.item(nome + marca, Y_INI + Y_PASSO * i, i == e.mode_sel)
            self.desenha_notas(Y_NOTAS)
            self.desenha_status(Y_RODAPE)

        elif e.mode_ui == 4:
            self.cabecalho("Acordes")
            itens = MODES[4]
            n = len(itens)
            ini = max(0, min(e.mode_sel - 1, n - 4))     # janela rolante de 4 itens
            for k in range(4):
                i = ini + k
                self.item(itens[i], Y_INI + Y_PASSO * k, i == e.mode_sel)
            if e.mode_sel < n - 1:
                raiz, tipo = e.mode_sel // 4, MIDI.CHORD_TYPES[e.mode_sel % 4]
                ms = midi.acorde_midis(raiz, tipo)
                self.texto(" ".join(midi.midi_to_name(m) for m in ms)[:16], 2, Y_NOTAS + 1)
                if e.acorde_ativo():
                    self.texto("Tocando...", 2, Y_RODAPE)
                else:
                    self.texto("Joy: tocar", 2, Y_RODAPE)

        else:
            self.desenha_afinador()

        self.oled.show_parcial(1)

    def chave_visual(self):
        """Resumo do que está na tela; só redesenha quando isso muda."""
        e = self.e
        if e.mode_ui == 2 and e.player is not None:
            pos = int(e.player.wav.posicao_s) if e.player.wav else 0
            return (2, e.player.indice, e.player.estado, pos, self.audio.volume, self.audio.mudo)
        return (e.mode_ui, e.mode_sel, tuple(e.notas_tocando), self.audio.volume,
                e.instrumento, e.oitava, e.sel_nota, self.midi.afinacao[e.sel_nota],
                e.acorde_ativo())


# ==========================================================
# [app]
# ==========================================================
# ============================================================
# app.py - Aplicação: monta o hardware e executa o laço principal
# ============================================================



class Aplicacao:
    def __init__(self):
        # Entradas
        self.joy = Joystick(pin_JOY_X, pin_JOY_Y, pin_JOY_SW,
                            LIMIAR, INVERTE_X, INVERTE_Y)
        enc_a = Pin(pin_ENC_A, Pin.IN, Pin.PULL_UP)
        enc_b = Pin(pin_ENC_B, Pin.IN, Pin.PULL_UP)
        enc_sw = Pin(pin_ENC_SW, Pin.IN, Pin.PULL_UP)
        self.enc = Encoder(enc_a, enc_b)
        self.btn_enc = Botao(enc_sw)
        self.teclado = Teclado(row_pins, col_pins, key_notes)

        # Display OLED
        i2c_oled = I2C(0, scl=Pin(OLED_SCL), sda=Pin(OLED_SDA), freq=400000)
        oled = SH1106_I2C(OLED_W, OLED_H, i2c_oled, addr=OLED_ADDR, rotate=180)

        # Armazenamento
        self.arquivos = montar_sd(SD_SCK, SD_MOSI, SD_MISO, SD_CS, SD_MOUNT)

        # Áudio e síntese
        self.audio = SaidaAudio()
        self.audio.abrir(SAMPLE_RATE, 1, IBUF_SINT)
        self.sintese = Sintese(midi)

        # Estado e interface
        self.e = Estado()
        self.tela = Tela(oled, self.e, midi, self.audio, self.arquivos)

    # ---------- troca de tela ----------
    def entrar_modo(self, antigo, novo):
        e = self.e
        if antigo == 2 and e.player is not None:
            self.audio.desmutar()
            e.player.parar()
        if novo == 2:
            self.audio.abrir(SAMPLE_RATE, 1, IBUF_PLAYER)
            e.player = Player(self.arquivos, self.audio.saida_wav, repetir=REPETIR_LISTA)
            if self.arquivos:
                e.player.selecionar(0)
            e.ultima_tecla = None
        else:
            self.audio.abrir(SAMPLE_RATE, 1, IBUF_SINT)
            if novo == 4:
                e.acorde_fim = utime.ticks_ms()

    # ---------- laços de cada família de modos ----------
    def loop_player(self, x, delta_enc, clique_enc):
        e = self.e
        player = e.player
        self.audio.ajustar_volume(delta_enc)
        if clique_enc:
            self.audio.alternar_mudo()
        tecla = self.teclado.scan(False)      # botões multimídia (linha 4)
        if tecla != e.ultima_tecla:           # só age na borda (um aperto = uma ação)
            e.ultima_tecla = tecla
            if tecla and self.arquivos:
                if tecla == "Play/Stop":
                    player.pausar_retomar()
                elif tecla == "Next":
                    player.proximo()
                elif tecla == "Prev":
                    player.anterior()
                elif tecla == "Reinicia":
                    player.reiniciar()

        if self.arquivos and abs(x) > self.joy.limiar:   # joystick em X: avança/retrocede
            player.pular(x)

        if player.estado == TOCANDO:
            player.atualizar()                # lê e envia o próximo bloco
        else:
            self.audio.escrever(SILENCIO)     # pausado: mantém o I2S alimentado

    def loop_sintetizador(self, mov_x, delta_enc, clique_enc):
        """Teclado / Instrumento / Acordes / Afinador (e Menu, em silêncio)."""
        e = self.e
        alvo = []
        instr = e.instrumento

        if e.mode_ui == 5:                                # ---- Afinador
            instr = "Afinador"
            nomes = self.teclado.scan(True)
            if nomes:                                     # tecla seleciona a nota
                e.sel_nota = NOTAS.index(nomes[0])
            elif mov_x:                                   # joystick navega entre as notas
                e.sel_nota = (e.sel_nota + mov_x) % 12
            if delta_enc:
                c = midi.afinacao[e.sel_nota] + delta_enc * PASSO_CENTS
                midi.afinacao[e.sel_nota] = max(-LIM_CENTS, min(LIM_CENTS, c))
            if clique_enc:                                # botão do encoder zera a afinação
                midi.afinacao[e.sel_nota] = 0
            alvo = [e.nota_midi(e.sel_nota)]

        else:
            self.audio.ajustar_volume(delta_enc)
            if e.mode_ui == 1 or e.mode_ui == 3:          # ---- Teclado / Instrumento
                if clique_enc:
                    e.oitava = e.oitava + 1 if e.oitava < 5 else 3
                alvo = [e.nota_midi(NOTAS.index(nm)) for nm in self.teclado.scan(True)]
            elif e.mode_ui == 4 and e.acorde_ativo():     # ---- Acordes
                alvo = midi.acorde_midis(e.acorde_idx // 4,
                                         MIDI.CHORD_TYPES[e.acorde_idx % 4])

        e.notas_tocando = alvo
        # sempre escreve (silêncio se vazio)
        self.audio.escrever(self.sintese.gerar(alvo, instr, self.audio.ganho))

    # ---------- laço principal ----------
    def executar(self):
        e = self.e
        chave_ant = None
        t_desenho = utime.ticks_ms()
        while True:
            x, mov_x, mov_y = self.joy.ler()
            modo_ant = e.mode_ui
            e.nav_mode(mov_x, mov_y, self.joy.clicou())
            if e.mode_ui != modo_ant:
                self.entrar_modo(modo_ant, e.mode_ui)

            delta_enc = self.enc.cliques()
            clique_enc = self.btn_enc.pressionado()

            if e.mode_ui == 2:
                self.loop_player(x, delta_enc, clique_enc)
            else:
                self.loop_sintetizador(mov_x, delta_enc, clique_enc)

            chave = self.tela.chave_visual()
            agora = utime.ticks_ms()
            if chave != chave_ant and utime.ticks_diff(agora, t_desenho) >= 250:
                chave_ant = chave
                t_desenho = agora
                self.tela.desenhar()
            self.tela.oled.show_parcial(1)


# ============================================================
# Ponto de entrada
# ============================================================
Aplicacao().executar()
