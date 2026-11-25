# ============================================================
# estado.py - Estado global da aplicação e navegação de menus
# ============================================================
import utime

from config import (MODES, DURACAO_ACORDE_MS, DURACAO_PREVIA_MS, MAPA_PADRAO, MAPA_MAX,
                    OITAVA_MIN, OITAVA_MAX, N_TECLAS)
from midi import ACORDES_LISTA, midi

# A lista de acordes depende do módulo midi, então é montada aqui
MODES[4] = ACORDES_LISTA + ["Teclado"]

# Modos (índices de MODES)
M_MENU, M_TECLADO, M_PLAYER, M_INSTR, M_ACORDES, M_AFINADOR, M_MAPA = 0, 1, 2, 3, 4, 5, 6

# Ao voltar para o modo Teclado, o cursor fica no item de onde se veio
_VOLTA_SEL = {M_INSTR: 0, M_ACORDES: 1, M_AFINADOR: 2, M_MAPA: 3}


class Estado:
    def __init__(self):
        self.mode_ui = M_MENU
        self.mode_sel = 0
        self.instrumento = "Piano"
        self.oitava = 4               # OITAVA_MIN..OITAVA_MAX (Left/Right no Instrumento)
        self.sel_nota = 0             # nota selecionada no Afinador (0 = C ... 11 = B)
        self.acorde_idx = 0           # acorde selecionado/tocando
        self.acorde_fim = utime.ticks_ms()
        self.mapa = list(MAPA_PADRAO)  # tecla -> semitons acima do Dó da oitava (configurável)
        self.map_tecla = 0            # tecla sendo editada no Mapeamento
        self.previa_fim = utime.ticks_ms()   # prévia sonora ao mudar a nota no Mapeamento
        self.teclas_mask = 0          # teclas tocadas agora (bit i = tecla i), para o display
        self.toque_ok = True          # False se o MCP23017 não respondeu na partida
        self.notas_tocando = []       # números MIDI soando agora (para o display)
        self.player = None

    # ---------- notas ----------
    def nota_midi(self, semitons):
        """Semitons acima do Dó da oitava atual -> número MIDI."""
        return 12 * (self.oitava + 1) + semitons

    def nota_tecla(self, i):
        return self.nota_midi(self.mapa[i])

    def acorde_ativo(self):
        return utime.ticks_diff(self.acorde_fim, utime.ticks_ms()) > 0

    def previa_ativa(self):
        return utime.ticks_diff(self.previa_fim, utime.ticks_ms()) > 0

    def _dispara_previa(self):
        self.previa_fim = utime.ticks_add(utime.ticks_ms(), DURACAO_PREVIA_MS)

    # ---------- navegação ----------
    def nav(self, mov_y, mov_x, ok):
        """mov_y: +1 desce, -1 sobe. mov_x: +1 direita, -1 esquerda. ok: botão Ok.
        Retorna True se o Ok foi usado pela navegação; no Player, quando o cursor está
        em "Player", o Ok não é consumido e o app o usa para pausar/retomar."""
        itens = MODES[self.mode_ui]
        n = len(itens)
        modo = self.mode_ui

        if mov_y:
            self.mode_sel = (self.mode_sel + mov_y) % n

        # ---- Left/Right conforme o modo
        if mov_x:
            if modo == M_ACORDES and self.mode_sel < n - 1:
                # pula de raiz em raiz (4 itens)
                self.mode_sel = (self.mode_sel + 4 * mov_x) % (n - 1)
            elif modo == M_INSTR:
                o = self.oitava + mov_x
                self.oitava = max(OITAVA_MIN, min(OITAVA_MAX, o))
            elif modo == M_AFINADOR:
                self.sel_nota = (self.sel_nota + mov_x) % 12
            elif modo == M_MAPA:
                self._mapa_valor(mov_x)

        if not ok:
            return False

        escolhido = itens[self.mode_sel]

        if modo == M_PLAYER and escolhido == "Player":
            return False                                   # Ok = pausar/retomar (app)

        if modo == M_ACORDES and self.mode_sel < n - 1:    # acorde: toca por 1,5 s
            self.acorde_idx = self.mode_sel
            self.acorde_fim = utime.ticks_add(utime.ticks_ms(), DURACAO_ACORDE_MS)
            return True
        if modo == M_INSTR and (escolhido == "Piano" or escolhido == "Sintetizador"):
            self.instrumento = escolhido
            return True
        if modo == M_AFINADOR and escolhido == "Zerar":
            midi.afinacao[self.sel_nota] = 0
            return True
        if modo == M_MAPA:
            if escolhido == "Padrao":
                self.mapa = list(MAPA_PADRAO)
                self._dispara_previa()
                return True
            if escolhido == "Tecla" or escolhido == "Nota":
                self._dispara_previa()                     # Ok repete a prévia
                return True

        if escolhido == "Menu":
            novo = M_MENU
        elif escolhido == "Teclado":
            novo = M_TECLADO
        elif escolhido == "Player":
            novo = M_PLAYER
        elif escolhido == "Instrumento":
            novo = M_INSTR
        elif escolhido == "Acordes":
            novo = M_ACORDES
        elif escolhido == "Afinador":
            novo = M_AFINADOR
        elif escolhido == "Mapeamento":
            novo = M_MAPA
        else:
            return True

        self.mode_ui = novo
        if novo == M_TECLADO:
            self.mode_sel = _VOLTA_SEL.get(modo, 0)
        elif novo == M_INSTR and self.instrumento == "Sintetizador":
            self.mode_sel = 1
        else:
            self.mode_sel = 0
        if novo == M_MAPA:
            self._dispara_previa()
        return True

    def _mapa_valor(self, passo):
        """Left/Right no Mapeamento: muda a tecla (item 0) ou a nota dela (item 1)."""
        sel = self.mode_sel
        if sel == 0:
            self.map_tecla = (self.map_tecla + passo) % N_TECLAS
            self._dispara_previa()
        elif sel == 1:
            v = self.mapa[self.map_tecla] + passo
            self.mapa[self.map_tecla] = max(0, min(MAPA_MAX, v))
            self._dispara_previa()
