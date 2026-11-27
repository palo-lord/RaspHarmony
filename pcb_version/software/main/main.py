# ============================================================
# RaspHarmony (versão PCB) - Sistema Embarcado Sintetizador e Reprodutor de Áudio
# ============================================================
# Nome: Paulo Sergio Gonçalves Júnior RA: 218474
# Nome: Vinicius Pedrillo de Souza RA: 258667
# ============================================================
# Ponto de entrada. Módulos (copiar a pasta lib para /lib no Pico):
#   config.py        pinos e constantes
#   encoder.py       Encoder (encoder rotativo, só giro = volume)
#   botoes.py        Botoes (Up, Down, Left, Right, Ok: curto/longo, por interrupção)
#   toque.py         TecladoToque (16 pads capacitivos, tempo de carga)
#   armazenamento.py montagem do SD e lista de WAVs
#   wavfile.py       WavFile
#   audio.py         SaidaAudio (I2S + volume)
#   midi.py          MIDI (notas, acordes, escalas)
#   sintese.py       Sintese (motor polifônico)
#   player.py        Player
#   estado.py        Estado (estado global + navegação + mapeamento das teclas)
#   ui.py            Tela (display OLED SH1109 SPI)
#   app.py           Aplicacao (hardware + laço principal)
# Dependências externas: sh1109.py, sdcard.py, mcp23017.py
# ============================================================
import micropython
import utime
import sys
import machine

micropython.alloc_emergency_exception_buf(100)  # permite ver erros dentro de IRQ

# Só com a fonte externa não há USB/Thonny para mostrar erros e a tensão leva um tempo
# para estabilizar: espera o SD, o OLED e o MCP23017 ligarem antes de inicializá-los.
utime.sleep_ms(500)

try:
    from app import Aplicacao
    Aplicacao().executar()
except Exception as err:
    # Sem USB o erro seria perdido: grava em /erro.txt e reinicia depois de 5 s.
    try:
        with open("/erro.txt", "w") as f:
            sys.print_exception(err, f)
    except Exception:
        pass
    sys.print_exception(err)
    utime.sleep(5)
    machine.reset()
