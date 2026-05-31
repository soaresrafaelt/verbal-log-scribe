#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Estruturador local: transforma o 'roteiro.txt' (dialogo medico/paciente) em
campos de prontuario (PEP), usando um LLM que roda LOCALMENTE via Ollama.

Tudo offline (LGPD): nenhuma informacao sai da maquina.

IMPORTANTE (seguranca clinica): o resultado e um RASCUNHO. O medico deve
SEMPRE revisar e validar antes de lancar no prontuario. O prompt instrui o
modelo a usar SOMENTE o que esta na transcricao e a escrever "Nao relatado"
quando faltar informacao, para evitar invencao de dados (alucinacao).

Uso:
    python estruturar.py            # usa roteiro.txt por padrao
    python estruturar.py outro.txt  # usa outro arquivo de transcricao
"""

import glob
import json
import os
import sys
import urllib.request
import urllib.error

import transcrever  # reusa o slug e a pasta de transcricoes (import barato: deps pesadas sao lazy)

# -------------------------------------------------------------------------
# Configuracoes
# -------------------------------------------------------------------------
MODELO = "llama3.1:8b"                 # modelo local (bom em portugues, cabe em 16 GB)
OLLAMA_URL = "http://localhost:11434/api/chat"

# Organizacao por etapa: le a transcricao da pasta 'transcricoes' e grava os
# prontuarios (JSON resolvido + versao legivel) na pasta 'prontuarios', nomeados
# pelo slug da consulta (herdado do roteiro) -> historico acumulado.
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
DIR_TRANSCRICOES = transcrever.DIR_TRANSCRICOES
DIR_PRONTUARIOS = os.path.join(DIR_BASE, "prontuarios")


def caminho_prontuario(slug: str, ext: str) -> str:
    """Caminho de uma saida de prontuario: prontuarios/<slug>.<ext> (ext = json|txt)."""
    return os.path.join(DIR_PRONTUARIOS, f"{slug}.{ext}")


def roteiro_mais_recente() -> str | None:
    """Devolve o roteiro modificado mais recentemente em 'transcricoes/', ou None."""
    arquivos = glob.glob(os.path.join(DIR_TRANSCRICOES, "*.txt"))
    return max(arquivos, key=os.path.getmtime) if arquivos else None

# Campos do prontuario que queremos extrair (chave interna -> rotulo legivel)
CAMPOS = {
    "queixa_principal": "Queixa Principal (QP)",
    "historia_doenca_atual": "Historia da Doenca Atual (HDA)",
    "antecedentes": "Antecedentes / Habitos",
    "hipotese_diagnostica": "Hipotese Diagnostica",
    "conduta": "Conduta / Plano",
}

# Instrucao do sistema: regras rigidas para nao inventar nada.
PROMPT_SISTEMA = """Voce e um assistente que estrutura transcricoes de consultas
medicas em campos de prontuario eletronico, em portugues do Brasil.

REGRAS OBRIGATORIAS (siga ao pe da letra):
- Use SOMENTE informacoes EXPLICITAMENTE ditas na transcricao. NUNCA infira,
  deduza, complete ou invente sintomas, diagnosticos, medicamentos, doses,
  exames ou condutas que nao foram verbalizados.
- Se nao houver informacao para um campo, escreva exatamente "Nao relatado".
  E MELHOR escrever "Nao relatado" do que arriscar uma informacao nao dita.
- "hipotese_diagnostica": preencha SOMENTE se o medico (o entrevistador)
  declarar explicitamente uma hipotese ou suspeita. Caso contrario, "Nao relatado".
  NUNCA proponha um diagnostico que o medico nao disse.
- "conduta": preencha SOMENTE com exames, encaminhamentos, prescricoes ou
  orientacoes que o medico declarou explicitamente. Caso contrario, "Nao relatado".
  NUNCA sugira condutas por conta propria.
- Seja conciso e objetivo, em linguagem clinica impessoal (3a pessoa).
- Responda APENAS com um JSON valido, sem texto antes ou depois."""


def montar_prompt_usuario(transcricao: str) -> str:
    """Monta a instrucao com a transcricao e o formato JSON esperado."""
    chaves = ", ".join(f'"{k}"' for k in CAMPOS)
    return (
        "Transcricao da consulta (cada linha: [horario] Falante N: fala):\n\n"
        f"{transcricao}\n\n"
        "Extraia as informacoes para um prontuario e responda APENAS com um JSON "
        f"com exatamente estas chaves: {chaves}.\n"
        "Cada valor deve ser um texto (string). Use \"Nao relatado\" quando faltar dado."
    )


def chamar_ollama(transcricao: str) -> dict:
    """Envia a transcricao ao Ollama local e devolve o dicionario de campos.

    Levanta excecao em caso de falha (quem chama trata e formata a mensagem):
      - ConnectionError: Ollama fora do ar / inacessivel.
      - ValueError: o modelo nao devolveu um JSON valido.
    """
    corpo = {
        "model": MODELO,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": montar_prompt_usuario(transcricao)},
        ],
        "stream": False,
        "format": "json",      # pede ao Ollama para garantir saida em JSON
        "options": {"temperature": 0},  # 0 = mais factual, menos "criativo"
    }
    dados = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=dados, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resposta:
            resultado = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.URLError as erro:
        raise ConnectionError(
            "Nao consegui falar com o Ollama em http://localhost:11434. "
            "Verifique se o servico esta rodando ('ollama serve') e se o modelo "
            f"foi baixado ('ollama pull {MODELO}')."
        ) from erro

    conteudo = resultado.get("message", {}).get("content", "").strip()
    try:
        return json.loads(conteudo)
    except json.JSONDecodeError as erro:
        raise ValueError(
            f"O modelo nao devolveu um JSON valido. Resposta recebida:\n{conteudo}"
        ) from erro


def estruturar_transcricao(transcricao: str, progresso=print) -> dict:
    """Pipeline de estruturacao: transcricao -> dict de campos do prontuario.

    Reutilizado pelo CLI e pelo painel. Garante que todas as chaves de CAMPOS
    existam (preenche faltantes com "Nao relatado"). Levanta excecao em falhas.
    """
    progresso("Estruturando a consulta em campos de prontuario (LLM local)...")
    campos = chamar_ollama(transcricao)
    return {k: campos.get(k, "Nao relatado") for k in CAMPOS}


def gerar_texto_legivel(campos: dict) -> str:
    """Monta a versao em texto, pronta para leitura e copia."""
    linhas = []
    for chave, rotulo in CAMPOS.items():
        valor = str(campos.get(chave, "Nao relatado")).strip() or "Nao relatado"
        linhas.append(f"{rotulo}:\n{valor}\n")
    return "\n".join(linhas)


def main():
    # Sem argumento, usa o roteiro mais recente da pasta 'transcricoes'.
    if len(sys.argv) > 1:
        caminho = sys.argv[1]
    else:
        caminho = roteiro_mais_recente()
        if caminho is None:
            print(
                f"\n[ERRO] Nenhum roteiro encontrado em '{DIR_TRANSCRICOES}'.\n"
                "       Rode antes: python transcrever.py caminho/do/audio.wav\n"
            )
            sys.exit(1)
        print(f"Usando o roteiro mais recente: {caminho}")

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            transcricao = arquivo.read().strip()
    except FileNotFoundError:
        print(f"\n[ERRO] Arquivo de transcricao nao encontrado: {caminho}\n")
        sys.exit(1)

    if not transcricao:
        print(f"\n[ERRO] O arquivo '{caminho}' esta vazio.\n")
        sys.exit(1)

    try:
        campos = estruturar_transcricao(transcricao)
    except (ConnectionError, ValueError) as erro:
        print(f"\n[ERRO] {erro}\n")
        sys.exit(1)

    # O prontuario herda o slug do roteiro (mesmo nome base) -> cadeia rastreavel.
    slug = transcrever.slug_de_arquivo(caminho)
    saida_json = caminho_prontuario(slug, "json")
    saida_txt = caminho_prontuario(slug, "txt")

    # Salva o JSON (para o painel copiar/colar ler depois)
    os.makedirs(DIR_PRONTUARIOS, exist_ok=True)
    with open(saida_json, "w", encoding="utf-8") as arquivo:
        json.dump(campos, arquivo, ensure_ascii=False, indent=2)

    # Salva e mostra a versao legivel
    texto = gerar_texto_legivel(campos)
    with open(saida_txt, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)

    print("\n" + "=" * 60)
    print("RASCUNHO DE PRONTUARIO (revise antes de lancar no PEP)")
    print("=" * 60 + "\n")
    print(texto)
    print("=" * 60)
    print(f"Salvo em '{saida_txt}' e '{saida_json}'.")
    print("ATENCAO: rascunho gerado por IA. O medico deve revisar e validar.\n")


if __name__ == "__main__":
    main()
