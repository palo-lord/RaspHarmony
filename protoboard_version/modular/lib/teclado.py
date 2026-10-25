# ============================================================
# teclado.py - Teclado matricial 4x4
# ============================================================
from machine import Pin


class Teclado:
    def __init__(self, row_pins, col_pins, key_notes):
        self.key_notes = key_notes
        self.rows = [Pin(p, Pin.OUT) for p in row_pins]
        self.cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in col_pins]

    def scan(self, flag_teclado):
        """flag_teclado=True: varre as 3 primeiras linhas e retorna a lista de notas.
        flag_teclado=False: varre a última linha (multimídia) e retorna a tecla ou None."""
        if flag_teclado:
            lista = []
            for r_idx, row in enumerate(self.rows):
                if r_idx == 3:
                    continue
                row.low()
                for c_idx, col in enumerate(self.cols):
                    if col.value() == 0:
                        lista.append(self.key_notes[r_idx][c_idx])
                row.high()
            return lista

        for r_idx, row in enumerate(self.rows):
            if r_idx != 3:
                continue
            row.low()
            for c_idx, col in enumerate(self.cols):
                if col.value() == 0:
                    row.low()
                    return self.key_notes[r_idx][c_idx]
            row.high()
        return None
