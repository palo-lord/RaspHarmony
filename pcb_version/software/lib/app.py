# ============================================================
# app.py - Aplicação: monta o hardware e executa o laço principal (versão PCB)
# ============================================================
from machine import Pin, I2C
import utime

import config as C
from encoder import Encoder
from botoes import Botoes
from mcp23017 import MCP23017
from toque import TecladoToque
from spibus import BarramentoSPI0, SH1106_SPI0
from armazenamento import montar_sd
from audio import SaidaAudio, SILENCIO
from midi import MIDI, midi
from sintese import Sintese
from player import Player
from estado import (Estado, M_PLAYER, M_INSTR, M_ACORDES, M_AFINADOR, M_MAPA)
from ui import Tela


class Aplicacao:
    def __init__(self):
        # Entradas
        self.botoes = Botoes()
        self.enc = Encoder(Pin(C.pin_ENC_A, Pin.IN, Pin.PULL_UP),
                           Pin(C.pin_ENC_B, Pin.IN, Pin.PULL_UP))

        # SPI0 de hardware compartilhado: SD (GP2/GP3/GP0) e OLED (GP18/GP19).
        # O SD é o estado de repouso; o OLED só pega o barramento ao enviar páginas.
        self.spi0 = BarramentoSPI0(0, C.SD_MISO)
        spi_sd = self.spi0.dispositivo(C.SD_SCK, C.SD_MOSI, C.SD_BAUD, mosi_ocioso=1)
        spi_oled = self.spi0.dispositivo(C.OLED_SCK, C.OLED_MOSI, C.OLED_BAUD)
        self.spi0.repouso = spi_sd

        # Display OLED SH1106 (SPI)
        oled = SH1106_SPI0(C.OLED_W, C.OLED_H, spi_oled, Pin(C.OLED_DC),
                           Pin(C.OLED_RES), Pin(C.OLED_CS), self.spi0,
                           rotate=C.OLED_ROTACAO)

        # Expansor de GPIO + teclado de toque (o app continua funcionando sem eles)
        self.toque = None
        try:
            rst = Pin(C.Exp_RST, Pin.OUT, value=0)     # pulso de reset (ativo em baixo)
            utime.sleep_ms(2)
            rst.value(1)
            utime.sleep_ms(5)
            i2c_exp = I2C(C.EXP_I2C_ID, scl=Pin(C.Exp_SCL), sda=Pin(C.Exp_SDA),
                          freq=C.EXP_I2C_FREQ)
            self.toque = TecladoToque(MCP23017(i2c_exp, C.EXP_ADDR))
        except OSError as err:
            print("MCP23017 indisponivel:", err)

        # Armazenamento (o SD volta a ser o dono do SPI0)
        self.spi0.repousar()
        self.arquivos = montar_sd(spi_sd, C.SD_CS, C.SD_MOUNT, C.SD_BAUD)

        # Áudio e síntese
        self.audio = SaidaAudio()
        self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_SINT)
        self.sintese = Sintese(midi)

        # Estado e interface
        self.e = Estado()
        self.e.toque_ok = self.toque is not None
        self.tela = Tela(oled, self.e, midi, self.audio, self.arquivos)

    # ---------- troca de tela ----------
    def entrar_modo(self, antigo, novo):
        e = self.e
        if antigo == M_PLAYER and e.player is not None:
            self.audio.desmutar()
            e.player.parar()
        e.teclas_mask = 0
        if novo == M_PLAYER:
            self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_PLAYER)
            e.player = Player(self.arquivos, self.audio.saida_wav, repetir=C.REPETIR_LISTA)
            if self.arquivos:
                e.player.selecionar(0)
        else:
            self.audio.abrir(C.SAMPLE_RATE, 1, C.IBUF_SINT)
            if novo == M_ACORDES:
                e.acorde_fim = utime.ticks_ms()
            elif novo == M_INSTR and self.toque is not None:
                self.toque.calibrar()          # linha de base com os pads livres

    # ---------- navegação ----------
    @staticmethod
    def _passo(b):
        """Botão apertado agora ou repetindo (segurado) -> 1; senão 0."""
        return 1 if (b.press or b.longo) else 0

    def navegar(self):
        """Lê os botões e atualiza o estado. Retorna True se o Ok ficou livre
        (só no Player, com o cursor em "Player")."""
        b = self.botoes
        e = self.e
        mov_y = self._passo(b.baixo) - self._passo(b.cima)
        if e.mode_ui == M_PLAYER:
            livre = not e.nav(mov_y, 0, b.ok.press) and b.ok.press
            self.controles_player()
            return livre
        e.nav(mov_y, self._passo(b.dir) - self._passo(b.esq), b.ok.press)
        return False

    def controles_player(self):
        """Left/Right no Player: clique curto = faixa anterior/próxima;
        segurado = pula PULO_S segundos a cada repetição."""
        b = self.botoes
        player = self.e.player
        if player is None or not self.arquivos:
            return
        if b.dir.curto:
            player.proximo()
        elif b.esq.curto:
            player.anterior()
        if b.dir.longo:
            player.pular_s(C.PULO_S)
        if b.esq.longo:
            player.pular_s(-C.PULO_S)

    # ---------- laços de cada família de modos ----------
    def loop_player(self, delta_enc, ok_livre):
        player = self.e.player
        self.audio.ajustar_volume(delta_enc)
        if ok_livre and self.arquivos:
            player.pausar_retomar()
        if player.estado == C.TOCANDO:
            player.atualizar()                # lê e envia o próximo bloco
        else:
            self.audio.escrever(SILENCIO)     # pausado: mantém o I2S alimentado

    def loop_sintetizador(self, delta_enc):
        """Instrumento / Acordes / Afinador / Mapeamento (menus ficam em silêncio)."""
        e = self.e
        alvo = []
        instr = e.instrumento

        if e.mode_ui == M_AFINADOR:
            instr = "Afinador"
            if delta_enc:
                c = midi.afinacao[e.sel_nota] + delta_enc * C.PASSO_CENTS
                midi.afinacao[e.sel_nota] = max(-C.LIM_CENTS, min(C.LIM_CENTS, c))
            alvo = [e.nota_midi(e.sel_nota)]
        else:
            self.audio.ajustar_volume(delta_enc)
            if e.mode_ui == M_INSTR:
                if self.toque is not None:     # o teclado só é varrido neste modo
                    e.teclas_mask = self.toque.varrer()
                    for i in range(C.N_TECLAS):
                        if (e.teclas_mask >> i) & 1:
                            m = e.nota_tecla(i)
                            if m not in alvo:
                                alvo.append(m)
                    alvo.sort()
            elif e.mode_ui == M_ACORDES and e.acorde_ativo():
                alvo = midi.acorde_midis(e.acorde_idx // 4,
                                         MIDI.CHORD_TYPES[e.acorde_idx % 4])
            elif e.mode_ui == M_MAPA and e.previa_ativa():
                alvo = [e.nota_tecla(e.map_tecla)]

        e.notas_tocando = alvo
        # sempre escreve (silêncio se vazio)
        self.audio.escrever(self.sintese.gerar(alvo, instr, self.audio.ganho))

    # ---------- laço principal ----------
    def executar(self):
        e = self.e
        chave_ant = None
        modo_desenhado = -1
        t_desenho = utime.ticks_add(utime.ticks_ms(), -C.UI_MIN_MS)
        while True:
            self.botoes.atualizar()
            modo_ant = e.mode_ui
            ok_livre = self.navegar()
            if e.mode_ui != modo_ant:
                self.entrar_modo(modo_ant, e.mode_ui)

            delta_enc = self.enc.cliques()
            if e.mode_ui == M_PLAYER:
                self.loop_player(delta_enc, ok_livre)
            else:
                self.loop_sintetizador(delta_enc)

            chave = self.tela.chave_visual()
            agora = utime.ticks_ms()
            if chave != chave_ant and (e.mode_ui != modo_desenhado or
                                       utime.ticks_diff(agora, t_desenho) >= C.UI_MIN_MS):
                chave_ant = chave
                modo_desenhado = e.mode_ui
                t_desenho = agora
                self.tela.desenhar()
            self.tela.oled.show_parcial(1)
