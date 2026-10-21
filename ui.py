# ============================================================
# ui.py - Interface gráfica no display OLED (128x64)
#
# Grade vertical usada em todas as telas:
#   y =  0        título (linha 0) + linha divisória em y = 9
#   y = 11 + 9*k  linhas de conteúdo (k = 0, 1, 2, ...)
#   y = 47        linha de notas tocando      (telas de teclado)
#   y = 56        última linha (status / botão "voltar")
# ============================================================
from config import (OLED_W, MODES, TOCANDO, LIM_CENTS,
                    Y_INI, Y_PASSO, Y_NOTAS, Y_RODAPE)
from midi import MIDI, NOTAS


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
            self.centro("{}/{} Vol:{}%".format(p.indice + 1, len(p.arquivos), self.audio.volume), 20)
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

        self.oled.show()

    def chave_visual(self):
        """Resumo do que está na tela; só redesenha quando isso muda."""
        e = self.e
        if e.mode_ui == 2 and e.player is not None:
            pos = int(e.player.wav.posicao_s) if e.player.wav else 0
            return (2, e.player.indice, e.player.estado, pos, self.audio.volume)
        return (e.mode_ui, e.mode_sel, tuple(e.notas_tocando), self.audio.volume,
                e.instrumento, e.oitava, e.sel_nota, self.midi.afinacao[e.sel_nota],
                e.acorde_ativo())
