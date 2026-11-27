# ============================================================
# estado.py - Estado global da aplicação e navegação de menus
# ============================================================
import utime

from config import (MODES, DURACAO_ACORDE_MS, DURACAO_PREVIA_MS, MAPAS_PADRAO, MAPA_MAX,
                    OITAVA_MIN, OITAVA_MAX, N_TECLAS)
from midi import ACORDES_LISTA, midi

# A lista de acordes depende do módulo midi, então é montada aqui
MODES[4] = ACORDES_LISTA + ["Teclado"]

# Modos (índices de MODES)
M_MENU, M_TECLADO, M_PLAYER, M_INSTR, M_ACORDES, M_AFINADOR, M_MAPA = 0, 1, 2, 3, 4, 5, 6

# Modos em que o teclado de toque está ativo (Teclado e todos os seus submodos)
MODOS_TECLADO = (M_TECLADO, M_INSTR, M_ACORDES, M_AFINADOR, M_MAPA)

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
        self.acorde_volta = 0         # acorde onde o cursor estava ao ir para o botão da direita
        self.acorde_fim = utime.ticks_ms()
        self.mapa = list(MAPAS_PADRAO[0])  # tecla -> semitons acima do Dó da oitava (configurável)
        self.padrao_idx = 0           # 0/1 = mapeamento padrão em uso; -1 = personalizado
        self.padrao_base = 0          # último padrão escolhido (Ok em "Padrao" volta para ele)
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
    def nav(self, mov_y, mov_x, ok, rapido=False):
        """mov_y: +1 desce, -1 sobe. mov_x: +1 direita, -1 esquerda. ok: botão Ok.
        Retorna True se o Ok foi usado pela navegação; no Player, quando o cursor está
        em "Player", o Ok não é consumido e o app o usa para pausar/retomar."""
        itens = MODES[self.mode_ui]
        n = len(itens)
        modo = self.mode_ui

        if modo == M_TECLADO:
            self._nav_teclado(mov_y, mov_x)
        elif modo == M_ACORDES:
            self._nav_acordes(mov_y, mov_x, rapido)
        else:
            if mov_y:
                self.mode_sel = (self.mode_sel + mov_y) % n
            if mov_x:
                if modo == M_INSTR:
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
                self._aplica_padrao(self.padrao_base)          # Ok = restaura o padrão escolhido
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

    def _nav_teclado(self, mov_y, mov_x):
        """Tela em duas colunas: esquerda = Instrumento/Acordes/Afinador (itens 0..2),
        direita = Mapeamento/Menu (itens 3..4). Up/Down gira dentro da coluna;
        Right/Left troca de coluna."""
        sel = self.mode_sel
        if mov_y:
            if sel < 3:
                sel = (sel + mov_y) % 3
            else:
                sel = 3 + (sel - 3 + mov_y) % 2
        if mov_x > 0 and sel < 3:
            sel = 3 if sel == 0 else 4
        elif mov_x < 0 and sel >= 3:
            sel -= 3
        self.mode_sel = sel

    def _nav_acordes(self, mov_y, mov_x, rapido):
        """Lista de acordes + botão da direita (último item de MODES[M_ACORDES]).
        Up/Down: 1 acorde (segurado: pula de raiz em raiz). Right: vai ao botão;
        Left (ou Up/Down) no botão: volta ao acorde em que estava."""
        n = len(MODES[M_ACORDES]) - 1          # só os acordes
        sel = self.mode_sel
        if sel >= n:
            if mov_y or mov_x < 0:
                self.mode_sel = self.acorde_volta
            return
        if mov_x > 0:
            self.acorde_volta = sel
            self.mode_sel = n
        elif mov_y:
            self.mode_sel = (sel + mov_y * (4 if rapido else 1)) % n

    def _aplica_padrao(self, idx):
        self.mapa = list(MAPAS_PADRAO[idx])
        self.padrao_idx = idx
        self.padrao_base = idx
        self._dispara_previa()

    def _detecta_padrao(self):
        """Índice do padrão que o mapa atual coincide (-1 = personalizado)."""
        for k in range(len(MAPAS_PADRAO)):
            if tuple(self.mapa) == MAPAS_PADRAO[k]:
                return k
        return -1

    def _mapa_valor(self, passo):
        """Left/Right no Mapeamento: tecla (item 0), nota dela (item 1) ou troca de padrão (item 2)."""
        sel = self.mode_sel
        if sel == 0:
            self.map_tecla = (self.map_tecla + passo) % N_TECLAS
            self._dispara_previa()
        elif sel == 1:
            v = self.mapa[self.map_tecla] + passo
            self.mapa[self.map_tecla] = max(0, min(MAPA_MAX, v))
            self.padrao_idx = self._detecta_padrao()
            self._dispara_previa()
        elif sel == 2:
            if self.padrao_idx < 0:                    # personalizado: volta ao último padrão
                novo = self.padrao_base
            else:
                novo = (self.padrao_idx + passo) % len(MAPAS_PADRAO)
            self._aplica_padrao(novo)
