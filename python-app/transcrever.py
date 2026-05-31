#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POC: Transcricao de consultas medicas (1 microfone).

Recebe um arquivo de audio (2 pessoas, PT-BR) e gera um arquivo
'roteiro.txt' com o texto de cada segmento rotulado por horario.

Tudo roda LOCALMENTE (offline). O unico acesso externo e o download dos
pesos do modelo na primeira execucao. Nenhum audio sai da maquina.

Uso:
    python transcrever.py caminho/do/audio.mp3
"""

import os
import sys

import glossario  # correcao/categorizacao por terminologia medica (so stdlib, offline)

# -------------------------------------------------------------------------
# Configuracoes ajustadas ao hardware (Apple Silicon M4, 16 GB, sem CUDA)
# -------------------------------------------------------------------------
# mlx-community/whisper-large-v3-turbo: modelo otimizado para Apple Silicon via MLX.
# Usa o Neural Engine do M4 — ~10-15x mais rapido que CPU com qualidade equivalente ao large-v3.
MODELO_WHISPER = "mlx-community/whisper-large-v3-turbo"
IDIOMA = "pt"

# Organizacao por etapa: cada saida vai para sua pasta (caminhos absolutos,
# ancorados na pasta do projeto, para funcionar tanto no CLI quanto no painel).
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_TRANSCRICOES = os.path.join(DIR_BASE, "transcricoes")


def slug_de_arquivo(caminho: str) -> str:
    return os.path.splitext(os.path.basename(caminho))[0]


def caminho_roteiro(slug: str) -> str:
    return os.path.join(DIR_TRANSCRICOES, f"{slug}.txt")


def formatar_tempo(segundos: float) -> str:
    segundos = int(segundos)
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    seg = segundos % 60
    return f"{horas:02d}:{minutos:02d}:{seg:02d}"


def carregar_token() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("HF_TOKEN")
    if not token or not token.startswith("hf_"):
        print(
            "\n[ERRO] Token do Hugging Face nao encontrado ou invalido.\n"
            "       Crie um arquivo '.env' nesta pasta com a linha:\n"
            "           HF_TOKEN=hf_seu_token_aqui\n"
        )
        sys.exit(1)
    return token


def _cortar_alucinacoes(segmentos, max_repeticoes=5):
    """Corta a cauda de alucinações do Whisper (silêncio transcrito como frases repetidas).

    Rastreia sequências contíguas de texto idêntico (normalizado). Quando uma sequência
    atinge max_repeticoes, trunca antes do início dela. Usa sequência contígua (não janela
    deslizante) para não cortar falas legítimas repetidas como 'não, não, não'.
    """
    textos = [s["texto"].strip().lower() for s in segmentos]
    run_start = 0
    run_len = 1
    for i in range(1, len(textos)):
        if textos[i] == textos[i - 1]:
            run_len += 1
            if run_len >= max_repeticoes:
                return segmentos[:run_start]
        else:
            run_start = i
            run_len = 1
    return segmentos


def transcrever_audio(caminho_audio: str, progresso=print):
    """Roda o mlx-whisper (Apple Silicon) e devolve segmentos com horario e texto."""
    import mlx_whisper

    progresso(f"Transcrevendo o audio... (1a vez baixa os pesos do modelo)")
    resultado = mlx_whisper.transcribe(
        caminho_audio,
        path_or_hf_repo=MODELO_WHISPER,
        language=IDIOMA,
        verbose=False,
    )

    # no_speech_prob alto indica que o Whisper reconhece que não há fala real no trecho.
    # Filtrar aqui preserva conteúdo real após pausas longas, enquanto descarta alucinações de silêncio.
    NO_SPEECH_THRESHOLD = 0.6
    segmentos = []
    for seg in resultado.get("segments", []):
        texto = seg.get("text", "").strip()
        no_speech_prob = seg.get("no_speech_prob", 0.0)
        if texto and no_speech_prob < NO_SPEECH_THRESHOLD:
            segmentos.append({
                "inicio": seg["start"],
                "texto": texto,
            })

    # Rede de segurança: remove cauda de frases repetidas caso o Whisper ainda alucine
    # com no_speech_prob baixo (raro, mas possível).
    segmentos = _cortar_alucinacoes(segmentos)
    return segmentos


def gerar_roteiro(segmentos, progresso=print):
    """Formata os segmentos do Whisper em linhas [HH:MM:SS] texto."""
    progresso("Gerando o roteiro...")

    saida = []
    correcoes = []
    for seg in segmentos:
        horario = formatar_tempo(seg["inicio"])
        texto = seg["texto"]
        texto, trocas = glossario.corrigir_texto(texto)
        correcoes.extend(trocas)
        if texto:
            saida.append(f"[{horario}] {texto}")

    if correcoes:
        progresso(f"Glossario: {len(correcoes)} termo(s) ajustado(s) pela terminologia medica.")
    return "\n".join(saida)


def gerar_roteiro_do_audio(caminho_audio: str, progresso=print) -> str:
    """Pipeline completo: audio -> roteiro (texto)."""
    segmentos = transcrever_audio(caminho_audio, progresso=progresso)
    if not segmentos:
        raise RuntimeError("Nenhuma fala foi reconhecida no audio.")
    return gerar_roteiro(segmentos, progresso=progresso)


def main():
    if len(sys.argv) < 2:
        print("Uso: python transcrever.py caminho/do/audio.mp3")
        sys.exit(1)

    caminho_audio = sys.argv[1]
    if not os.path.isfile(caminho_audio):
        print(f"\n[ERRO] Arquivo de audio nao encontrado: {caminho_audio}\n")
        sys.exit(1)

    try:
        roteiro = gerar_roteiro_do_audio(caminho_audio)
    except Exception as erro:
        print(
            f"\n[ERRO] Falha ao transcrever o audio: {erro}\n"
            "       Verifique se o formato e suportado (mp3, wav, m4a) e se o ffmpeg esta instalado.\n"
        )
        sys.exit(1)

    saida = caminho_roteiro(slug_de_arquivo(caminho_audio))
    os.makedirs(DIR_TRANSCRICOES, exist_ok=True)
    with open(saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(roteiro + "\n")

    print(f"\nPronto! Roteiro salvo em '{saida}'.")

    print("\nTermos identificados (glossario):")
    print(glossario.formatar_categorias(glossario.categorizar_texto(roteiro)))
    print()


if __name__ == "__main__":
    main()
