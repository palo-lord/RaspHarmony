# ============================================================
# ui.py - Interface gráfica horizontal no display OLED SH1109 (128x64)
#
# Layout comum a todas as telas:
#   y =  0..10   barra de título invertida (título | extra | alto-falante + volume)
#   y = 13..53   área de conteúdo: lista à esquerda + painel/ícone à direita
#   y = 54       linha divisória do rodapé (nas telas com dicas)
#   y = 55..63   rodapé: dica de teclas ou abas selecionáveis
# Fonte 8x8 do framebuf (16 colunas x 8 linhas), só ASCII.
# ============================================================
import math
import utime

from config import OLED_W, MODES, TOCANDO, LIM_CENTS, N_TECLAS
from midi import MIDI, NOTAS
from estado import (M_MENU, M_TECLADO, M_PLAYER, M_INSTR, M_ACORDES, M_AFINADOR, M_MAPA)

_DE = "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ"
_PARA = "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN"


def ascii_(s):
    """Troca letras acentuadas (a fonte do OLED só tem ASCII)."""
    r = ""
    for c in s:
        if ord(c) > 127:
            k = _DE.find(c)
            c = _PARA[k] if k >= 0 else "?"
        r += c
    return r


class Tela:
    def __init__(self, oled, estado, midi, audio, arquivos):
        self.oled = oled
        self.e = estado
        self.midi = midi
        self.audio = audio
        self.arquivos = arquivos
        self._rot_ms = 0                 # tempo acumulado tocando (gira o disco)
        self._t_rot = utime.ticks_ms()
        self._cache_nome = ("", "")

    # ---------- primitivas ----------
    def texto(self, s, x, y, c=1):
        self.oled.text(s, x, y, c)

    def centro(self, s, x, larg, y, c=1):
        """Texto centralizado na faixa [x, x+larg)."""
        self.oled.text(s, x + max(0, (larg - 8 * len(s)) // 2), y, c)

    def direita(self, s, x_fim, y, c=1):
        self.oled.text(s, x_fim - 8 * len(s), y, c)

    def barra_titulo(self, titulo, extra=None):
        o = self.oled
        o.fill_rect(0, 0, OLED_W, 11, 1)
        o.text(titulo, 2, 2, 0)
        if extra:
            o.text(extra, 56, 2, 0)
        s = str(self.audio.volume)
        x = 126 - 8 * len(s)
        o.text(s, x, 2, 0)
        xi = x - 10                              # ícone do alto-falante (7x7)
        o.fill_rect(xi, 4, 2, 3, 0)
        o.vline(xi + 2, 3, 5, 0)
        o.vline(xi + 3, 2, 7, 0)
        if self.audio.volume:
            o.vline(xi + 5, 4, 3, 0)

    def rodape(self, s):
        self.oled.hline(0, 54, OLED_W, 1)
        self.texto(s, 2, 56)

    def lista(self, itens, sel, x, y, larg, alt=9, passo=10, recuo=3, ini=0, qtd=None):
        """Lista vertical com a linha selecionada invertida."""
        o = self.oled
        if qtd is None:
            qtd = len(itens)
        for k in range(qtd):
            i = ini + k
            yy = y + k * passo
            if i == sel:
                o.fill_rect(x, yy, larg, alt, 1)
                cor = 0
            else:
                cor = 1
            o.text(itens[i], x + recuo, yy + (alt - 8) // 2, cor)

    def aba(self, s, x, y, larg, ativa):
        o = self.oled
        if ativa:
            o.fill_rect(x, y, larg, 9, 1)
        else:
            o.rect(x, y, larg, 9, 1)
        self.centro(s, x, larg, y + 1, 0 if ativa else 1)

    @staticmethod
    def fmt_tempo(s):
        s = int(s)
        return "{:02d}:{:02d}".format(s // 60, s % 60)

    @staticmethod
    def janela(txt, t, larg):
        """Letreiro rolante para nomes maiores que 'larg' caracteres."""
        if len(txt) <= larg:
            return txt
        extra = len(txt) - larg
        off = t % (extra + 4)
        if off > extra:
            off = extra
        return txt[off:off + larg]

    def triangulo(self, x, y, h, direita):
        wd = h // 2
        meio = h // 2
        for c in range(wd):
            metade = meio * (wd - c) // wd
            xx = x + c if direita else x + wd - 1 - c
            self.oled.vline(xx, y + meio - metade, 2 * metade + 1, 1)

    def circulo(self, cx, cy, r):
        try:
            self.oled.ellipse(cx, cy, r, r, 1)
        except AttributeError:                   # firmware sem ellipse()
            self.oled.rect(cx - r, cy - r, 2 * r + 1, 2 * r + 1, 1)

    def barra_progresso(self, x, y, larg, alt, frac):
        self.oled.rect(x, y, larg, alt, 1)
        if frac > 0:
            self.oled.fill_rect(x, y, max(1, int(larg * min(frac, 1.0))), alt, 1)

    # ---------- ícones (40x30 aprox.) ----------
    def icone_piano(self, x, y):
        o = self.oled
        o.rect(x, y, 40, 30, 1)
        for i in range(1, 5):
            o.vline(x + 8 * i, y + 14, 16, 1)
        for i in (1, 2, 4):
            o.fill_rect(x + 8 * i - 2, y + 1, 5, 14, 1)

    def icone_player(self, x, y):
        cx, cy = x + 20, y + 15
        self.circulo(cx, cy, 14)
        self.circulo(cx, cy, 4)
        self.triangulo(cx - 2, cy - 3, 6, True)

    # ---------- componentes ----------
    def texto_notas(self):
        notas = self.e.notas_tocando
        if not notas:
            return "-"
        return " ".join(self.midi.midi_to_name(m) for m in notas)

    # ---------- telas ----------
    def tela_menu(self):
        e = self.e
        self.barra_titulo("RaspHarmony")
        self.lista(MODES[M_MENU], e.mode_sel, 0, 16, 78, alt=13, passo=15, recuo=4)
        n = len(self.arquivos)
        self.texto("SD:{} WAV".format(n) if n else "Sem SD/WAV", 2, 46)
        if e.mode_sel == 0:
            self.icone_piano(86, 16)
        else:
            self.icone_player(86, 16)
        self.rodape("U/D:Mover OK:Ir")

    def miniatura_teclado(self, y=49, h=14):
        """Os 16 pads em fileira, na ordem física da PCB (da esquerda p/ direita: pad 16 ... pad 1).
        Cada pad acende enquanto a tecla está apertada. Ajuste x/y/larg/h aqui se o
        arranjo da placa for diferente."""
        o = self.oled
        mask = self.e.teclas_mask
        for p in range(N_TECLAS):
            i = N_TECLAS - 1 - p                 # índice da tecla (pad = i + 1)
            x = 2 + 8 * p
            if (mask >> i) & 1:
                o.fill_rect(x, y, 6, h, 1)
            else:
                o.rect(x, y, 6, h, 1)

    def tela_teclado(self):
        e = self.e
        o = self.oled
        sel = e.mode_sel
        self.barra_titulo("Teclado")
        self.lista(["Instrum.", "Acordes", "Afinador"], sel, 0, 13, 65, recuo=1)
        o.vline(66, 12, 34, 1)
        self.lista(["Mapa", "Menu"], sel - 3, 68, 13, 59)
        self.texto("{} O{}".format("Pno" if e.instrumento == "Piano" else "Sin", e.oitava), 68, 36)
        o.hline(0, 46, OLED_W, 1)
        self.miniatura_teclado()

    def tela_instrumento(self):
        e = self.e
        o = self.oled
        self.barra_titulo("Instrumento")
        itens = MODES[M_INSTR]
        self.lista(itens, e.mode_sel, 0, 13, OLED_W, recuo=14)
        for i in range(2):                      # botão de opção: instrumento atual
            cor = 0 if i == e.mode_sel else 1
            o.rect(3, 13 + 10 * i + 2, 5, 5, cor)
            if itens[i] == e.instrumento:
                o.fill_rect(4, 13 + 10 * i + 3, 3, 3, cor)
        if e.toque_ok:
            self.texto(("O{} {}".format(e.oitava, self.texto_notas()))[:16], 2, 43)
        else:
            self.texto("Sem MCP23017!", 2, 43)
        for i in range(N_TECLAS):               # atividade das 16 teclas
            x = 8 + 7 * i
            if (e.teclas_mask >> i) & 1:
                o.fill_rect(x, 54, 6, 9, 1)
            else:
                o.rect(x, 54, 6, 9, 1)

    def tela_acordes(self):
        e = self.e
        o = self.oled
        self.barra_titulo("Acordes")
        itens = MODES[M_ACORDES]
        n = len(itens) - 1                           # só os acordes; o último item é o botão
        no_botao = e.mode_sel >= n
        idx = e.acorde_volta if no_botao else e.mode_sel
        ini = max(0, min(idx - 1, n - 3))            # janela rolante de 3 itens
        self.lista(itens, -1 if no_botao else idx, 0, 13, 118, ini=ini, qtd=3)
        o.rect(123, 13, 4, 29, 1)                    # barra de rolagem
        th = max(3, 29 * 3 // n)
        o.fill_rect(123, 13 + (29 - th) * ini // max(1, n - 3), 4, th, 1)
        ms = self.midi.acorde_midis(idx // 4, MIDI.CHORD_TYPES[idx % 4])
        s = " ".join(self.midi.midi_to_name(m) for m in ms)
        if e.acorde_ativo():
            o.fill_rect(0, 43, OLED_W, 10, 1)
            self.centro(s, 0, OLED_W, 44, 0)
        else:
            self.centro(s, 0, OLED_W, 44, 1)
        self.texto("OK:Toca", 2, 56)
        self.aba(itens[n], 66, 55, 60, no_botao)     # botão à direita, sempre à mão

    def tela_afinador(self):
        e = self.e
        o = self.oled
        midi = self.midi
        sel = e.sel_nota
        self.barra_titulo("Afinador")
        for k in range(5):                           # nota selecionada no centro
            x = 4 + 24 * k
            nome = NOTAS[(sel + k - 2) % 12]
            if k == 2:
                o.fill_rect(x, 12, 22, 14, 1)
                self.centro(nome, x, 22, 15, 0)
            else:
                o.rect(x, 12, 22, 14, 1)
                self.centro(nome, x, 22, 15, 1)
        cents = midi.afinacao[sel]
        m = e.nota_midi(sel)
        self.texto("F {:.2f}Hz".format(midi.freq_afinada(m)), 2, 29)
        self.direita("{:+d}c".format(cents), 126, 29)
        self.texto("P {:.2f}Hz".format(midi.midi_to_freq(m)), 2, 38)
        self.direita(midi.midi_to_name(m), 126, 38)
        o.rect(14, 46, 101, 8, 1)                    # medidor: centro = nota certa
        o.vline(64, 44, 10, 1)
        o.fill_rect(64 + cents * 50 // LIM_CENTS - 1, 48, 3, 5, 1)
        self.aba("Zerar", 2, 55, 61, e.mode_sel == 0)
        self.aba("Teclado", 66, 55, 60, e.mode_sel == 1)

    def tela_mapa(self):
        e = self.e
        o = self.oled
        sel = e.mode_sel
        pad = "Pad.{}".format(e.padrao_idx + 1) if e.padrao_idx >= 0 else "Pers."
        self.barra_titulo("Mapa", pad)
        nome = self.midi.midi_to_name(e.nota_tecla(e.map_tecla))
        self.aba("Tecla:{:02d}".format(e.map_tecla + 1), 2, 12, 61, sel == 0)
        self.aba("Nota:" + nome, 65, 12, 61, sel == 1)
        # Sequência de notas na ordem física: o pad 16 é o primeiro e o pad 1 o último
        for p in range(N_TECLAS):
            i = N_TECLAS - 1 - p
            x = 32 * (p % 4)
            y = 23 + 8 * (p // 4)
            s = self.midi.midi_to_name(e.nota_tecla(i))
            if i == e.map_tecla:
                o.fill_rect(x, y, 32, 8, 1)
                self.centro(s, x, 32, y, 0)
            else:
                self.centro(s, x, 32, y, 1)
        pd = "<Pad:{}>".format(e.padrao_idx + 1) if e.padrao_idx >= 0 else "<Pad:*>"
        self.aba(pd, 2, 55, 61, sel == 2)
        self.aba(MODES[M_MAPA][3], 66, 55, 60, sel == 3)

    def disco(self, cx, cy, r, rot_ms):
        """Disco de vinil girando (1 volta a cada 2 s enquanto toca)."""
        o = self.oled
        self.circulo(cx, cy, r)
        self.circulo(cx, cy, 2)
        a = rot_ms * 6.2832 / 2000
        c = math.cos(a)
        s = math.sin(a)
        o.line(cx + round(3 * c), cy + round(3 * s), cx + round((r - 2) * c), cy + round((r - 2) * s), 1)
        o.line(cx - round(3 * c), cy - round(3 * s), cx - round((r - 5) * c), cy - round((r - 5) * s), 1)

    def _nome_faixa(self, p):
        """Nome da faixa atual sem pasta/.wav e sem acentos (em cache)."""
        caminho = p.arquivos[p.indice]
        if self._cache_nome[0] != caminho:
            nome = ascii_(caminho.split("/")[-1])
            if nome.lower().endswith(".wav"):
                nome = nome[:-4]
            self._cache_nome = (caminho, nome)
        return self._cache_nome[1]

    def tela_player(self):
        e = self.e
        o = self.oled
        p = e.player
        sel = e.mode_sel
        extra = None
        if p is not None and self.arquivos:
            extra = "{}/{}".format(p.indice + 1, len(p.arquivos))
        self.barra_titulo("Player", extra)

        agora = utime.ticks_ms()
        if p is not None and p.estado == TOCANDO:
            self._rot_ms += utime.ticks_diff(agora, self._t_rot)
        self._t_rot = agora
        self.disco(64, 22, 9, self._rot_ms)          # y = 13..31

        if p is None or not self.arquivos:
            self.centro("Sem arquivos", 0, OLED_W, 35)
            self.centro("WAV no SD", 0, OLED_W, 45)
            dica = "OK:Sair" if sel == 1 else "OK:--"
        else:
            nome = self._nome_faixa(p)
            # nome (16 caracteres cabem na linha; maior que isso vira letreiro rolante)
            self.centro(self.janela(nome, agora // 400, 16), 0, OLED_W, 33)
            pos = p.wav.posicao_s if p.wav else 0
            dur = p.wav.duracao_s if p.wav else 0
            self.texto(self.fmt_tempo(pos), 0, 44)
            self.barra_progresso(42, 45, 44, 6, pos / dur if dur > 0 else 0)
            self.direita(self.fmt_tempo(dur), 128, 44)
            dica = "OK:Sair" if sel == 1 else ("OK:Pausa" if p.estado == TOCANDO else "OK:Tocar")
        self.texto(dica, 2, 56)
        self.aba("Menu", 88, 55, 39, sel == 1)

    def desenhar(self):
        self.oled.fill(0)
        modo = self.e.mode_ui
        if modo == M_MENU:
            self.tela_menu()
        elif modo == M_TECLADO:
            self.tela_teclado()
        elif modo == M_PLAYER:
            self.tela_player()
        elif modo == M_INSTR:
            self.tela_instrumento()
        elif modo == M_ACORDES:
            self.tela_acordes()
        elif modo == M_AFINADOR:
            self.tela_afinador()
        else:
            self.tela_mapa()
        self.oled.show_parcial(1)

    def chave_visual(self):
        """Resumo do que está na tela; só redesenha quando isso muda."""
        e = self.e
        if e.mode_ui == M_PLAYER and e.player is not None:
            p = e.player
            pos = int(p.wav.posicao_s) if p.wav else 0
            anim = 0                       # disco girando / nome rolando
            if self.arquivos and (p.estado == TOCANDO or len(self._nome_faixa(p)) > 16):
                anim = utime.ticks_ms() // 200
            return (M_PLAYER, e.mode_sel, p.indice, p.estado, pos,
                    self.audio.volume, anim)
        return (e.mode_ui, e.mode_sel, tuple(e.notas_tocando), e.teclas_mask,
                self.audio.volume, e.instrumento, e.oitava, e.sel_nota,
                self.midi.afinacao[e.sel_nota], e.acorde_ativo(), e.map_tecla,
                tuple(e.mapa), e.padrao_idx)
