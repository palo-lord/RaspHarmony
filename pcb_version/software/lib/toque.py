# ============================================================
# toque.py - Teclado de toque capacitivo DIY (16 pads no MCP23017)
#
# Hardware (inalterado): cada pad tem um resistor de 1 MΩ para o GND
# (pulldown) e está ligado a um GPIO do MCP23017.
#
# Princípio (tempo de DESCARGA):
#   1. Os 16 GPIOs viram SAÍDA em nível alto -> os pads carregam até 3V3.
#      Ficam assim por TOQUE_CARGA_US para garantir a carga completa.
#   2. Os 16 GPIOs viram ENTRADA (uma escrita I2C de 2 bytes) -> cada pad
#      descarrega pelo resistor com constante de tempo R x C.
#   3. Depois de um atraso EXATO 'd' (espera ativa com IRQs desligadas), uma
#      única leitura do GPIO diz quais pads ainda estão em nível alto.
# O dedo soma capacitância -> descarga mais lenta -> o pad fica alto por mais tempo.
#
# Amostragem em tempo equivalente: em vez de várias leituras seguidas num mesmo
# ciclo (resolução = duração de uma leitura I2C, ~100 µs), cada varredura faz
# vários ciclos, cada um com UMA leitura num atraso diferente:
#     d = atraso0, atraso0 + passo, atraso0 + 2*passo, ...
# O número de ciclos em que o pad ainda estava alto x passo = tempo de descarga
# (somado a uma latência fixa, igual para todos, que a linha de base absorve).
# A resolução passa a ser TOQUE_PASSO_US (~8 µs) em vez de ~100 µs.
#
# Janela automática: na calibração, uma busca grossa encontra o tempo de descarga
# dos pads livres e posiciona a janela [atraso0, atraso0 + passos*passo] em volta
# deles (com TOQUE_FOLGA_US de sobra para o dedo).
#
# Detecção: limiar por pad (o maior entre TOQUE_LIMIAR_US e TOQUE_K_RUIDO x ruído
# medido na calibração), histerese para soltar (TOQUE_SOLTAR_PCT), debounce de
# 2 varreduras, linha de base em ponto fixo (x16) acompanhando a deriva só com o
# pad livre, e recalibração do pad "preso" depois de TOQUE_PRESO_MS.
#
# Use teste_toque.py para ver os tempos e ajustar os TOQUE_* do config.py.
# Só varra este teclado no modo Instrumento: cada varredura ocupa o I2C.
# ============================================================
from array import array
from micropython import const
import machine
import micropython
import utime

import config as C

# Registradores com IOCON.BANK = 0 (A e B intercalados, escrita sequencial A,B)
_IODIR = const(0x00)     # IODIRA/IODIRB
_IPOL = const(0x02)      # IPOLA/IPOLB
_GPINTEN = const(0x04)   # GPINTENA/GPINTENB
_GPPU = const(0x0C)      # GPPUA/GPPUB
_GPIO = const(0x12)      # GPIOA/GPIOB
_OLAT = const(0x14)      # OLATA/OLATB

_GRANDE = const(1 << 29)


@micropython.viper
def _somar_altos(mascara: int, cnt):
    """cnt[i] += 1 para cada bit i em nível alto na máscara (rápido, em viper)."""
    c = ptr16(cnt)
    i = 0
    while mascara:
        if mascara & 1:
            c[i] = c[i] + 1
        mascara = mascara >> 1
        i += 1


class TecladoToque:
    def __init__(self, mcp):
        # 'mcp' é um MCP23017 já inicializado. Só usamos o I2C e o endereço dele:
        # o acesso rápido é direto nos registradores.
        self.i2c = mcp._i2c
        self.addr = mcp._address
        self.n = C.N_TECLAS

        self.carga = C.TOQUE_CARGA_US
        self.passo = C.TOQUE_PASSO_US
        self.repeticoes = max(1, C.TOQUE_REPETICOES)
        self.sem_irq = C.TOQUE_SEM_IRQ
        self.preso_ms = C.TOQUE_PRESO_MS

        self._saida = bytes((0x00, 0x00))       # IODIR: todos como saída (carrega)
        self._entrada = bytes((0xFF, 0xFF))     # IODIR: todos como entrada (descarrega)
        self._buf = bytearray(2)
        self._cnt = array('H', [0] * self.n)    # ciclos em nível alto (por pad)
        self._acum = array('i', [0] * self.n)

        self.t = array('i', [0] * self.n)       # tempo de descarga medido (µs)
        self.base16 = array('i', [0] * self.n)  # linha de base (µs x 16)
        self.lim16 = array('i', [0] * self.n)   # limiar para tocar (µs x 16)
        self.sol16 = array('i', [0] * self.n)   # limiar para soltar (µs x 16)
        self.ruido = array('i', [0] * self.n)   # variação na calibração (µs)
        self._desde = array('i', [0] * self.n)  # ticks_ms em que o pad virou candidato

        self.tocado = 0      # máscara das teclas tocadas (bit i = tecla i)
        self._cand = 0       # candidatos (com histerese, antes do debounce)
        self._ant = 0

        # Diagnóstico (preenchido na calibração)
        self.defeito = 0     # pads que não descarregam (sempre altos): ignorados
        self.rapido = 0      # pads que já estão em 0 na 1ª leitura (sem resolução)
        self.saturado = 0    # pads livres que passam do fim da janela

        self.erros = 0       # quantas vezes o I2C falhou e foi recuperado

        self._config_regs()
        self._definir_janela(C.TOQUE_ATRASO0_US, C.TOQUE_PASSOS)
        self.calibrar()

    # ---------- configuração e recuperação do I2C ----------
    def _config_regs(self):
        """Configuração explícita: sem inversão, sem interrupção e SEM pull-up
        (um pull-up ligado impediria a descarga pelo resistor de 1 MΩ).
        Também é chamada depois de um reset do MCP23017."""
        w = self.i2c.writeto_mem
        a = self.addr
        w(a, _IPOL, b'\x00\x00')
        w(a, _GPINTEN, b'\x00\x00')
        w(a, _GPPU, b'\x00\x00')
        w(a, _OLAT, b'\xff\xff')      # latch alto: só age quando o pino vira saída
        w(a, _IODIR, self._entrada)

    def _recuperar(self):
        """Depois de um erro de I2C (ruído do dedo pode deixar o MCP23017 preso no meio
        de um byte, segurando o SDA): 9 clocks + STOP para soltar o barramento, reset de
        hardware do MCP23017, I2C recriado (timeout curto) e registradores reescritos.
        A linha de base da calibração é mantida."""
        self.erros += 1
        self.tocado = self._cand = self._ant = 0
        try:
            scl = machine.Pin(C.Exp_SCL, machine.Pin.OPEN_DRAIN, value=1)
            sda = machine.Pin(C.Exp_SDA, machine.Pin.OPEN_DRAIN, value=1)
            utime.sleep_us(10)
            for _ in range(9):              # escravo preso: dá clock até ele soltar o SDA
                if sda.value():
                    break
                scl.value(0)
                utime.sleep_us(5)
                scl.value(1)
                utime.sleep_us(5)
            sda.value(0)                    # condição de STOP
            utime.sleep_us(5)
            scl.value(1)
            utime.sleep_us(5)
            sda.value(1)
            utime.sleep_us(5)
            rst = machine.Pin(C.Exp_RST, machine.Pin.OUT, value=0)   # reset do MCP23017
            utime.sleep_ms(1)
            rst.value(1)
            utime.sleep_ms(2)
            self.i2c = machine.I2C(C.EXP_I2C_ID, scl=machine.Pin(C.Exp_SCL),
                                   sda=machine.Pin(C.Exp_SDA), freq=C.EXP_I2C_FREQ,
                                   timeout=5000)
            self._config_regs()
        except OSError:
            pass                            # a próxima varredura tenta de novo

    # ---------- medição ----------
    def _definir_janela(self, atraso0, passos):
        self.atraso0 = atraso0
        self.passos = passos
        self._atrasos = [atraso0 + k * self.passo for k in range(passos)]

    def _ciclo(self, atraso):
        """Carrega, solta e lê o GPIO uma vez, 'atraso' µs depois de soltar.
        Retorna a máscara dos pads ainda em nível alto."""
        i2c = self.i2c
        addr = self.addr
        buf = self._buf
        i2c.writeto_mem(addr, _IODIR, self._saida)      # carrega (saída em nível alto)
        if self.carga:
            utime.sleep_us(self.carga)                  # garante a carga completa
        # Trecho crítico: nada pode atrasar entre soltar e ler (IRQs desligadas).
        # O I2C do RP2040 funciona por polling, então não depende de interrupção.
        if self.sem_irq:
            irq = machine.disable_irq()
        try:
            i2c.writeto_mem(addr, _IODIR, self._entrada)    # solta: começa a descarregar
            t0 = utime.ticks_us()
            if atraso:
                while utime.ticks_diff(utime.ticks_us(), t0) < atraso:
                    pass
            i2c.readfrom_mem_into(addr, _GPIO, buf)
        finally:
            if self.sem_irq:
                machine.enable_irq(irq)
        return buf[0] | (buf[1] << 8)

    def _varredura(self, atrasos, cnt):
        """Um ciclo por atraso; cnt[i] = em quantos ciclos o pad i estava alto."""
        for i in range(self.n):
            cnt[i] = 0
        for d in atrasos:
            alto = self._ciclo(d)
            if not alto:
                break               # todos já descarregaram: os próximos também estariam em 0
            _somar_altos(alto, cnt)

    def medir(self):
        """Mede o tempo de descarga de cada pad (µs) em self.t."""
        cnt = self._cnt
        acum = self._acum
        n = self.n
        r = self.repeticoes
        for i in range(n):
            acum[i] = 0
        for _ in range(r):
            self._varredura(self._atrasos, cnt)
            for i in range(n):
                acum[i] += cnt[i]
        t = self.t
        p = self.passo
        a0 = self.atraso0
        for i in range(n):
            t[i] = a0 + (acum[i] * p) // r

    # ---------- calibração ----------
    def _ajustar_janela(self):
        """Busca grossa dos tempos dos pads livres e posiciona a janela fina."""
        grosso = self.passo * 4
        atrasos = list(range(0, C.TOQUE_T_MAX_US + 1, grosso))
        n_at = len(atrasos)
        cnt = self._cnt
        tmin = _GRANDE
        tmax = 0
        defeito = 0
        for _ in range(4):
            self._varredura(atrasos, cnt)
            for i in range(self.n):
                if cnt[i] >= n_at:              # não descarregou até T_MAX: defeito
                    defeito |= 1 << i
                    continue
                v = cnt[i] * grosso
                if v < tmin:
                    tmin = v
                if v > tmax:
                    tmax = v
        self.defeito = defeito
        if tmin == _GRANDE:                     # nenhum pad válido: mantém a janela do config
            return
        atraso0 = max(0, tmin - 2 * grosso)
        largura = tmax + grosso - atraso0 + C.TOQUE_FOLGA_US
        passos = (largura + self.passo - 1) // self.passo
        passos = max(4, min(C.TOQUE_PASSOS_MAX, passos))
        self._definir_janela(atraso0, passos)

    def calibrar(self, ciclos=C.TOQUE_CICLOS_CAL, tentativas=3):
        """Define a linha de base com os pads livres. Não encoste nas teclas."""
        n = self.n
        try:
            if C.TOQUE_JANELA_AUTO:
                self._ajustar_janela()
            self.medir()                        # aquecimento (descartado)
            soma = [0] * n
            mn = [_GRANDE] * n
            mx = [0] * n
            t = self.t
            for _ in range(ciclos):
                self.medir()
                for i in range(n):
                    v = t[i]
                    soma[i] += v
                    if v < mn[i]:
                        mn[i] = v
                    if v > mx[i]:
                        mx[i] = v
        except OSError:                         # MCP não respondeu: recupera e tenta de novo
            self._recuperar()
            if tentativas > 0:
                return self.calibrar(ciclos, tentativas - 1)
            return

        t_fim = self.atraso0 + self.passos * self.passo
        rapido = 0
        saturado = 0
        for i in range(n):
            self.base16[i] = (soma[i] << 4) // ciclos
            self.ruido[i] = mx[i] - mn[i]
            lim = max(C.TOQUE_LIMIAR_US, C.TOQUE_K_RUIDO * self.ruido[i])
            self.lim16[i] = lim << 4
            self.sol16[i] = (lim * C.TOQUE_SOLTAR_PCT // 100) << 4
            if (self.defeito >> i) & 1:
                continue
            if mx[i] <= self.atraso0 and self.atraso0 == 0:
                rapido |= 1 << i
            if mx[i] >= t_fim:
                saturado |= 1 << i
        self.rapido = rapido
        self.saturado = saturado
        self.tocado = self._cand = self._ant = 0
        #if self.defeito or rapido or saturado:
            #print("toque: defeito=%04x rapido=%04x saturado=%04x (rode teste_toque.py)"
                  #% (self.defeito, rapido, saturado))

    # ---------- detecção ----------
    def varrer(self):
        """Faz uma varredura e retorna a máscara das teclas tocadas (bit i = tecla i)."""
        try:
            self.medir()
        except OSError:                 # MCP não respondeu: recupera o I2C e considera tudo solto
            self._recuperar()
            for i in range(self.n):     # não deixa valores velhos congelados em self.t
                self.t[i] = self.base16[i] >> 4
            return 0
        t = self.t
        b = self.base16
        lim = self.lim16
        sol = self.sol16
        desde = self._desde
        preso = self.preso_ms
        defeito = self.defeito
        cand = self._cand
        agora = utime.ticks_ms()
        for i in range(self.n):
            bit = 1 << i
            if defeito & bit:
                continue
            d = (t[i] << 4) - b[i]                 # diferença para a base (µs x 16)
            if cand & bit:
                if d < sol[i]:                     # histerese: solta só bem abaixo do limiar
                    cand &= ~bit
                elif preso and utime.ticks_diff(agora, desde[i]) > preso:
                    b[i] = t[i] << 4               # pad preso: assume o valor atual como base
                    cand &= ~bit
            elif d > lim[i]:
                cand |= bit
                desde[i] = agora
            elif d < -lim[i]:
                b[i] += d >> 2                     # base muito acima (ex.: depois de "preso"): volta rápido
            elif d < sol[i]:
                b[i] += d >> 4                     # pad livre: acompanha a deriva devagar
        self._cand = cand
        # debounce: só muda depois de duas varreduras seguidas concordando
        ant = self._ant
        self.tocado = (cand & ant) | (self.tocado & (cand | ant))
        self._ant = cand
        return self.tocado

    def base_us(self, i):
        """Linha de base do pad i em µs."""
        return self.base16[i] >> 4

    @staticmethod
    def teclas(mascara):
        """Máscara -> lista de índices de teclas (0..15), em ordem."""
        return [i for i in range(16) if (mascara >> i) & 1]


# ============================================================
# Modo INT: o pino INT do MCP23017 mede o tempo de descarga.
#
# Configuração: INTCON = 0xFFFF e DEFVAL = 0xFFFF (INT ativa quando o pino cai para 0),
# GPINTEN habilita UM pad por vez e IOCON.MIRROR = 1 (INTA e INTB juntos, não importa
# em qual deles a PCB ligou o GP Exp_INT). O Pico mede, com o timer de 1 µs do RP2040,
# o tempo entre soltar o pad e a borda de descida do INT. A resolução deixa de depender
# da duração da transação I2C (~100 µs) e passa a ser ~1 µs.
# ============================================================
_IOCON = const(0x0A)
_DEFVAL = const(0x06)    # DEFVALA/B + INTCONA/B em sequência (0x06..0x09)


@micropython.viper
def _esperar_int(mascara: int, timeout: int) -> int:
    """Devolve os µs até o pino INT (bit 'mascara' do SIO GPIO_IN) cair, ou 'timeout'."""
    gpio = ptr32(0xD0000004)      # SIO GPIO_IN
    tim = ptr32(0x40054028)       # TIMERAWL: contador de 1 µs
    t0 = int(tim[0])
    while True:
        dt = (int(tim[0]) - t0) & 0xFFFFFF
        if (int(gpio[0]) & mascara) == 0:
            return dt
        if dt >= timeout:
            return timeout


class TecladoToqueINT(TecladoToque):
    def __init__(self, mcp):
        self.timeout = C.TOQUE_INT_TIMEOUT_US
        self._pin_int = machine.Pin(C.Exp_INT, machine.Pin.IN, machine.Pin.PULL_UP)
        self._mask_int = 1 << C.Exp_INT
        # Escrita única de 6 bytes a partir de IODIR: IODIR=0 (carrega), IPOL=0, GPINTEN = só o pad i
        self._cargas = [bytes((0, 0, 0, 0, (1 << i) & 0xFF, (1 << i) >> 8))
                        for i in range(C.N_TECLAS)]
        super().__init__(mcp)

    def _config_regs(self):
        super()._config_regs()
        i2c = self.i2c
        a = self.addr
        # INT em OR (MIRROR = bit 6), compara com DEFVAL = 1 (dispara quando o pino cai)
        v = i2c.readfrom_mem(a, _IOCON, 1)[0]
        i2c.writeto_mem(a, _IOCON, bytes((v | 0x40,)))
        i2c.writeto_mem(a, _DEFVAL, b'\xff\xff\xff\xff')

    def _ajustar_janela(self):
        # Sem janela: o tempo vem direto do INT. Só procura pads com defeito.
        self._definir_janela(0, max(4, self.timeout // self.passo))
        self.medir()
        defeito = 0
        for i in range(self.n):
            if self.t[i] >= self.timeout:
                defeito |= 1 << i
        self.defeito = defeito

    def medir(self):
        """Mede o tempo de descarga de cada pad (µs) em self.t, um pad por vez."""
        i2c = self.i2c
        a = self.addr
        buf = self._buf
        acum = self._acum
        t = self.t
        mask = self._mask_int
        tout = self.timeout
        r = self.repeticoes
        cargas = self._cargas
        entrada = self._entrada
        carga = self.carga
        sem_irq = self.sem_irq
        for i in range(self.n):
            soma = 0
            for _ in range(r):
                i2c.writeto_mem(a, _IODIR, cargas[i])       # carrega o pad i e arma o INT dele
                if carga:
                    utime.sleep_us(carga)
                if sem_irq:
                    irq = machine.disable_irq()
                try:
                    i2c.writeto_mem(a, _IODIR, entrada)     # solta: começa a descarregar
                    soma += _esperar_int(mask, tout)
                finally:
                    if sem_irq:
                        machine.enable_irq(irq)
                i2c.readfrom_mem_into(a, _GPIO, buf)        # lê o GPIO: limpa o INT latcheado
            acum[i] = soma
            t[i] = soma // r


# Mantém o resto do projeto inalterado: quem importa TecladoToque recebe o modo escolhido.
TecladoToqueI2C = TecladoToque
if C.TOQUE_USAR_INT:
    TecladoToque = TecladoToqueINT
