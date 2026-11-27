# ============================================================
# teclas.py - Filtro de sustentação das teclas de toque
#
# Recebe a máscara "crua" do TecladoToque.varrer() e devolve a máscara filtrada:
#   - uma tecla detectada continua ativa por 'segura_ms' depois da ÚLTIMA detecção
#     (duração mínima da nota + tolerância a falhas de uma varredura);
#   - guarda a ORDEM em que as teclas foram apertadas. Com mais teclas do que vozes, o
#     sintetizador mantém as notas mais antigas em vez de trocar de nota conforme a altura.
# ============================================================
import utime


class FiltroTeclas:
    def __init__(self, n, segura_ms):
        self.n = n
        self.segura = segura_ms
        self.ate = [0] * n       # ticks_ms em que a tecla deixa de valer
        self.ordem = []          # índices das teclas ativas, na ordem em que foram apertadas
        self.mascara = 0

    def zerar(self):
        del self.ordem[:]
        self.mascara = 0

    def atualizar(self, mascara):
        """Aplica a máscara crua desta varredura; retorna a máscara filtrada."""
        agora = utime.ticks_ms()
        fim = utime.ticks_add(agora, self.segura)
        ate = self.ate
        ordem = self.ordem
        ativa = self.mascara
        for i in range(self.n):
            bit = 1 << i
            if mascara & bit:
                ate[i] = fim
                if not ativa & bit:
                    ativa |= bit
                    ordem.append(i)
            elif ativa & bit and utime.ticks_diff(agora, ate[i]) >= 0:
                ativa &= ~bit
                ordem.remove(i)
        self.mascara = ativa
        return ativa

