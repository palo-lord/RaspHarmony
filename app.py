# ============================================================
# app.py - Aplicação: monta o hardware e executa o laço principal
# ============================================================
from machine import Pin, I2C
from sh1106 import SH1106_I2C
import utime

import config as C
from encoder import Encoder
from botao import Botao
from joystick import Joystick
from teclado import Teclado
from armazenamento import montar_sd
from audio import SaidaAudio, SILENCIO
from midi import MIDI, NOTAS, midi
from sintese import Sintese
from player import Player
from estado import Estado
from ui import Tela


class Aplicacao:
    def __init__(self):
        # Entradas
        self.joy = Joystick(C.pin_JOY_X, C.pin_JOY_Y, C.pin_JOY_SW,
                            C.LIMIAR, C.INVERTE_X, C.INVERTE_Y)
        enc_a = Pin(C.pin_ENC_A, Pin.IN, Pin.PULL_UP)
        enc_b = Pin(C.pin_ENC_B, Pin.IN, Pin.PULL_UP)
        enc_sw = Pin(C.pin_ENC_SW, Pin.IN, Pin.PULL_UP)
        self.enc = Encoder(enc_a, enc_b)
        self.btn_enc = Botao(enc_sw)
        self.teclado = Teclado(C.row_pins, C.col_pins, C.key_notes)

        # Display OLED
        i2c_oled = I2C(0, scl=Pin(C.OLED_SCL), sda=Pin(C.OLED_SDA), freq=400000)
        oled = SH1106_I2C(C.OLED_W, C.OLED_H, i2c_oled, addr=C.OLED_ADDR, rotate=180)

        # Armazenamento
        self.arquivos = montar_sd(C.SD_SCK, C.SD_MOSI, C.SD_MISO, C.SD_CS, C.SD_MOUNT)

        # Áudio e síntese
        self.audio = SaidaAudio()
        self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_SINT)
        self.sintese = Sintese(midi)

        # Estado e interface
        self.e = Estado()
        self.tela = Tela(oled, self.e, midi, self.audio, self.arquivos)

    # ---------- troca de tela ----------
    def entrar_modo(self, antigo, novo):
        e = self.e
        if antigo == 2 and e.player is not None:
            e.player.parar()
        if novo == 2:
            self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_PLAYER)
            e.player = Player(self.arquivos, self.audio.saida_wav, repetir=C.REPETIR_LISTA)
            if self.arquivos:
                e.player.selecionar(0)
            e.ultima_tecla = None
        else:
            self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_SINT)
            if novo == 4:
                e.acorde_fim = utime.ticks_ms()

    # ---------- laços de cada família de modos ----------
    def loop_player(self, x, delta_enc):
        e = self.e
        player = e.player
        self.audio.ajustar_volume(delta_enc)

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

        if player.estado == C.TOCANDO:
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
                c = midi.afinacao[e.sel_nota] + delta_enc * C.PASSO_CENTS
                midi.afinacao[e.sel_nota] = max(-C.LIM_CENTS, min(C.LIM_CENTS, c))
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
        while True:
            x, mov_x, mov_y = self.joy.ler()
            modo_ant = e.mode_ui
            e.nav_mode(mov_x, mov_y, self.joy.clicou())
            if e.mode_ui != modo_ant:
                self.entrar_modo(modo_ant, e.mode_ui)

            delta_enc = self.enc.cliques()
            clique_enc = self.btn_enc.pressionado()

            if e.mode_ui == 2:
                self.loop_player(x, delta_enc)
            else:
                self.loop_sintetizador(mov_x, delta_enc, clique_enc)

            chave = self.tela.chave_visual()
            if chave != chave_ant:
                chave_ant = chave
                self.tela.desenhar()
