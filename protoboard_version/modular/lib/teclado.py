# ============================================================
# teclado.py - Teclado matricial 4x4
# ============================================================
from machine import Pin
import utime

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
