#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POC: Transcricao com diarizacao de falantes (1 microfone).

Recebe um arquivo de audio de uma consulta medica (2 pessoas, PT-BR) e gera
um arquivo 'roteiro.txt' onde cada fala esta rotulada por falante e com horario.

Tudo roda LOCALMENTE (offline). O unico acesso externo e o download dos
pesos dos modelos na primeira execucao. Nenhum audio sai da maquina.

Uso:
    python transcrever.py caminho/do/audio.mp3
"""

import os
import sys

import glossario  # correcao/categorizacao por terminologia medica (so stdlib, offline)

# -------------------------------------------------------------------------
# Configuracoes ajustadas ao hardware (Apple Silicon M4, 16 GB, sem CUDA)
# -------------------------------------------------------------------------
MODELO_WHISPER = "large-v3"   # cabe bem em 16 GB; troque por "large-v3" se quiser mais precisao
IDIOMA = "pt"               # portugues do Brasil
NUM_FALANTES = 2            # consulta = entrevistador + entrevistado (sempre 2)
USAR_GLOSSARIO = True       # corrige a grafia de termos medicos no roteiro (glossario.json)

# Organizacao por etapa: cada saida vai para sua pasta (caminhos absolutos,
# ancorados na pasta do projeto, para funcionar tanto no CLI quanto no painel).
# Cada consulta tem um "slug" (identificador unico) e seus arquivos sao nomeados
# por ele em cada pasta -> o historico acumula, nada e sobrescrito.
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_TRANSCRICOES = os.path.join(DIR_BASE, "transcricoes")


def slug_de_arquivo(caminho: str) -> str:
    """Deriva o identificador da consulta a partir do nome do arquivo (sem extensao).

    Ex.: 'audios/consulta_teste.wav' -> 'consulta_teste'. Assim o roteiro herda o
    nome do audio e a cadeia audio -> roteiro -> prontuario fica rastreavel.
    """
    return os.path.splitext(os.path.basename(caminho))[0]


def caminho_roteiro(slug: str) -> str:
    """Caminho do roteiro de uma consulta: transcricoes/<slug>.txt."""
    return os.path.join(DIR_TRANSCRICOES, f"{slug}.txt")


def formatar_tempo(segundos: float) -> str:
    """Converte segundos (float) para o formato HH:MM:SS."""
    segundos = int(segundos)
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    seg = segundos % 60
    return f"{horas:02d}:{minutos:02d}:{seg:02d}"


def carregar_token() -> str:
    """Le o token do Hugging Face do arquivo .env (variavel HF_TOKEN)."""
    from dotenv import load_dotenv
    load_dotenv()  # le o arquivo .env da pasta atual
    token = os.getenv("HF_TOKEN")
    if not token or not token.startswith("hf_"):
        print(
            "\n[ERRO] Token do Hugging Face nao encontrado ou invalido.\n"
            "       Crie um arquivo '.env' nesta pasta com a linha:\n"
            "           HF_TOKEN=hf_seu_token_aqui\n"
            "       (O token e gratuito e serve so para baixar o modelo uma vez.)\n"
        )
        sys.exit(1)
    return token


def transcrever_audio(caminho_audio: str, progresso=print):
    """Roda o faster-whisper e devolve a lista de palavras com horario."""
    from faster_whisper import WhisperModel

    progresso(f"Carregando modelo de transcricao ('{MODELO_WHISPER}')... (1a vez baixa os pesos)")
    # device="cpu" + compute_type="int8": rapido e leve no M4, sem depender de CUDA
    modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")

    progresso("Transcrevendo o audio... (pode demorar alguns minutos)")
    segmentos, _info = modelo.transcribe(
        caminho_audio,
        language=IDIOMA,
        word_timestamps=True,  # precisamos do horario de cada palavra para alinhar com o falante
    )

    # Achata todos os segmentos numa unica lista de palavras com inicio/fim/texto
    palavras = []
    for segmento in segmentos:
        if segmento.words is None:
            continue
        for palavra in segmento.words:
            palavras.append({
                "inicio": palavra.start,
                "fim": palavra.end,
                "texto": palavra.word,
            })
    return palavras


def diarizar_audio(caminho_audio: str, token: str, progresso=print):
    """Roda o pyannote para descobrir QUEM falou em cada intervalo de tempo."""
    from pyannote.audio import Pipeline
    import torch

    progresso("Carregando modelo de identificacao de falantes... (1a vez baixa os pesos)")
    # pyannote.audio 4.x usa o modelo novo 'community-1' (autocontido).
    # O parametro de autenticacao chama-se 'token' nesta versao.
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1",
        token=token,
    )
    # Roda em CPU para estabilidade nesta POC (evita instabilidade do MPS)
    pipeline.to(torch.device("cpu"))

    progresso("Identificando os falantes... (pode demorar alguns minutos)")
    # Forca 2 falantes: melhora muito a precisao, pois sabemos que sao sempre 2 pessoas
    resultado = pipeline(caminho_audio, num_speakers=NUM_FALANTES)

    # Na pyannote.audio 4.x o retorno e um objeto DiarizeOutput.
    # Usamos a versao 'exclusive' (sem sobreposicao de falas), ideal para alinhar
    # com a transcricao. Ela e uma Annotation com o metodo itertracks.
    diarizacao = resultado.exclusive_speaker_diarization

    # Converte para uma lista de segmentos: inicio, fim e rotulo do falante
    segmentos_falante = []
    for trecho, _, falante in diarizacao.itertracks(yield_label=True):
        segmentos_falante.append({
            "inicio": trecho.start,
            "fim": trecho.end,
            "falante": falante,
        })
    return segmentos_falante


def falante_da_palavra(palavra, segmentos_falante):
    """Descobre a qual falante uma palavra pertence, por sobreposicao de tempo."""
    melhor_falante = None
    maior_sobreposicao = 0.0
    for seg in segmentos_falante:
        # Sobreposicao entre o intervalo da palavra e o intervalo do falante
        inicio = max(palavra["inicio"], seg["inicio"])
        fim = min(palavra["fim"], seg["fim"])
        sobreposicao = fim - inicio
        if sobreposicao > maior_sobreposicao:
            maior_sobreposicao = sobreposicao
            melhor_falante = seg["falante"]
    return melhor_falante


def gerar_roteiro(palavras, segmentos_falante, progresso=print):
    """Alinha palavras aos falantes e agrupa em linhas de fala."""
    progresso("Gerando o roteiro...")

    # Mapeia os rotulos internos do pyannote (ex: SPEAKER_00) para "Falante 1/2",
    # na ordem em que cada um aparece pela primeira vez (quem fala primeiro = Falante 1).
    mapa_falantes = {}
    proximo_numero = 1

    linhas = []           # lista final de falas
    fala_atual = None     # acumula palavras consecutivas do mesmo falante

    for palavra in palavras:
        rotulo = falante_da_palavra(palavra, segmentos_falante)
        if rotulo is None:
            # Palavra sem falante identificado (silencio/ruido); pula
            continue

        if rotulo not in mapa_falantes:
            mapa_falantes[rotulo] = proximo_numero
            proximo_numero += 1
        numero_falante = mapa_falantes[rotulo]

        if fala_atual is None:
            # Primeira fala
            fala_atual = {
                "falante": numero_falante,
                "inicio": palavra["inicio"],
                "texto": palavra["texto"].strip(),
            }
        elif numero_falante == fala_atual["falante"]:
            # Mesmo falante: continua a mesma linha
            fala_atual["texto"] += palavra["texto"]
        else:
            # Mudou de falante: fecha a linha anterior e comeca outra
            linhas.append(fala_atual)
            fala_atual = {
                "falante": numero_falante,
                "inicio": palavra["inicio"],
                "texto": palavra["texto"].strip(),
            }

    if fala_atual is not None:
        linhas.append(fala_atual)

    # Monta o texto final no formato [HH:MM:SS] Falante N: texto, corrigindo a
    # grafia de termos medicos pelo glossario (so o texto da fala; nunca o prefixo).
    saida = []
    correcoes = []
    for linha in linhas:
        horario = formatar_tempo(linha["inicio"])
        texto = linha["texto"].strip()
        if USAR_GLOSSARIO:
            texto, trocas = glossario.corrigir_texto(texto)
            correcoes.extend(trocas)
        saida.append(f"[{horario}] Falante {linha['falante']}: {texto}")

    if correcoes:
        progresso(f"Glossario: {len(correcoes)} termo(s) ajustado(s) pela terminologia medica.")
    return "\n".join(saida)


def gerar_roteiro_do_audio(caminho_audio: str, token: str, progresso=print) -> str:
    """Pipeline completo: audio -> roteiro (texto). Reutilizado pelo CLI e pelo painel.

    'progresso' e uma funcao (texto -> None) usada para reportar cada etapa;
    no CLI e o 'print', no painel e o callback que atualiza o status do job.
    Levanta excecao em caso de falha (quem chama trata e formata a mensagem).
    """
    palavras = transcrever_audio(caminho_audio, progresso=progresso)
    if not palavras:
        raise RuntimeError("Nenhuma fala foi reconhecida no audio.")

    segmentos_falante = diarizar_audio(caminho_audio, token, progresso=progresso)
    return gerar_roteiro(palavras, segmentos_falante, progresso=progresso)


def main():
    # --- Validacao do argumento de entrada ---
    if len(sys.argv) < 2:
        print("Uso: python transcrever.py caminho/do/audio.mp3")
        sys.exit(1)

    caminho_audio = sys.argv[1]
    if not os.path.isfile(caminho_audio):
        print(f"\n[ERRO] Arquivo de audio nao encontrado: {caminho_audio}\n")
        sys.exit(1)

    token = carregar_token()

    try:
        palavras = transcrever_audio(caminho_audio)
    except Exception as erro:
        print(
            f"\n[ERRO] Falha ao transcrever o audio: {erro}\n"
            "       Verifique se o formato e suportado (mp3, wav, m4a) e se o ffmpeg esta instalado.\n"
        )
        sys.exit(1)

    if not palavras:
        print("\n[ERRO] Nenhuma fala foi reconhecida no audio. Verifique o arquivo.\n")
        sys.exit(1)

    try:
        segmentos_falante = diarizar_audio(caminho_audio, token)
    except Exception as erro:
        print(
            f"\n[ERRO] Falha ao identificar os falantes: {erro}\n"
            "       Causas comuns: token invalido, ou termos de uso do modelo\n"
            "       'pyannote/speaker-diarization-community-1' ainda nao aceitos.\n"
            "       Aceite em: https://huggingface.co/pyannote/speaker-diarization-community-1\n"
        )
        sys.exit(1)

    roteiro = gerar_roteiro(palavras, segmentos_falante)

    # O roteiro herda o nome do audio (slug) e vai para a pasta de transcricoes.
    saida = caminho_roteiro(slug_de_arquivo(caminho_audio))
    os.makedirs(DIR_TRANSCRICOES, exist_ok=True)
    with open(saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(roteiro + "\n")

    print(f"\nPronto! Roteiro salvo em '{saida}'.")
    print("Dica: como os papeis sao fixos, normalmente 'Falante 1' e o medico (quem fala primeiro).")

    # Categoriza os termos do glossario que apareceram (ajuda a classificar a consulta).
    print("\nTermos identificados (glossario):")
    print(glossario.formatar_categorias(glossario.categorizar_texto(roteiro)))
    print()


if __name__ == "__main__":
    main()
