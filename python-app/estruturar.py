#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Estruturador: transforma o 'roteiro.txt' (dialogo medico/paciente) em
campos de prontuario (PEP), usando um LLM via API (Gemini, OpenAI ou Anthropic).

O provedor e selecionado automaticamente pela presenca de chaves no .env:
  prioridade: GEMINI_API_KEY > OPENAI_API_KEY > ANTHROPIC_API_KEY

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
import time

from dotenv import load_dotenv

import transcrever  # reusa o slug e a pasta de transcricoes (import barato: deps pesadas sao lazy)
from anonimizar import anonimizar

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

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

PROMPT_SISTEMA = """Você é um assistente que estrutura transcrições de consultas médicas em campos de prontuário eletrônico, em português do Brasil.

A transcrição é uma sequência de segmentos no formato [HH:MM:SS] texto, sem rótulos de falante. Identifique quem é o médico e quem é o paciente pelo contexto: o médico faz perguntas clínicas, nomeia hipóteses diagnósticas e prescreve condutas; o paciente relata sintomas e responde às perguntas.

ESTILO DE REDAÇÃO:
Escreva como um médico redige um prontuário — impessoal, 3ª pessoa, telegráfico, com terminologia clínica padrão. Converta linguagem coloquial em equivalente técnico SEM acrescentar informação (ex.: "dor de barriga há 3 dias" → "dor abdominal há 3 dias"; "tonteira ao levantar" → "tontura ortostática"; "queimação no peito depois de comer" → "pirose pós-prandial"). Use abreviações de uso corrente (HAS, DM2, QP, HDA, BEG, etc.) apenas quando o conteúdo verbalizado as justificar.

REGRAS INVIOLÁVEIS — siga ao pé da letra:
1. FIDELIDADE: Use SOMENTE informações EXPLICITAMENTE ditas na transcrição. Nunca infira, deduza, complete ou invente sintomas, diagnósticos, medicamentos, doses, exames ou condutas não verbalizados.
2. PROIBIÇÃO DE INFERÊNCIAS CLÍNICAS: Não deduza condição a partir de medicamento ou vice-versa. Exemplos: metformina ≠ DM2; losartana ≠ HAS; levotiroxina ≠ hipotireoidismo; AAS ≠ cardiopatia. Registre apenas o que foi dito, não o que o medicamento implica.
3. PERGUNTAS NÃO SÃO FATOS: Pergunta do médico não confirma presença de sintoma. Registre apenas respostas confirmadas ou negadas pelo paciente.
4. CONFLITOS NA TRANSCRIÇÃO: Quando houver correção ou contradição, mantenha apenas a informação mais recente. Quando houver conflito sem correção explícita, registre a versão mais conservadora.
5. EXAME FÍSICO: Nunca crie achados de exame físico automaticamente. Se o médico não descreveu o exame, use "Não relatado". Nunca escreva achados normais que não foram verbalizados.
6. HIPÓTESES DIAGNÓSTICAS: Preserve expressões de incerteza ("suspeita de", "provável", "possivelmente", "pode ser"). Nunca transforme hipótese em diagnóstico confirmado. Preencha este campo SOMENTE se o médico declarou explicitamente uma hipótese ou suspeita — caso contrário, "Não relatado".
7. CONDUTA: Preencha SOMENTE com exames, prescrições, orientações e encaminhamentos que o médico declarou explicitamente. Registre doses, vias e posologia apenas se verbalizadas. Caso contrário, "Não relatado".
8. CAMPOS VAZIOS: Se não houver informação para um campo, escreva exatamente "Não relatado". Nunca deixe campo em branco.

REGRAS SOAP (quando o template usar seções S/O/A/P):
- Subjetivo (S): apenas o que o paciente relatou espontaneamente ou em resposta a perguntas.
- Objetivo (O): apenas exame físico, sinais vitais e achados VERBALIZADOS pelo médico durante o atendimento. Nunca crie achados normais automaticamente.
- Avaliação (A): apenas hipóteses ou diagnósticos DECLARADOS pelo médico.
- Plano (P): apenas prescrições, exames, orientações e encaminhamentos VERBALIZADOS pelo médico.

VERIFICAÇÃO OBRIGATÓRIA — execute antes de gerar a resposta:
Para cada campo preenchido, confirme: "Esta informação foi explicitamente verbalizada na transcrição?".
Se a resposta for não, substitua por "Não relatado".
Remova: diagnósticos não verbalizados pelo médico; medicamentos não prescritos; exame físico criado automaticamente; sintomas inferidos de perguntas não respondidas.

Responda APENAS com um JSON válido, sem texto antes ou depois."""


def montar_prompt_usuario(transcricao: str) -> str:
    """Monta a instrucao com a transcricao e o formato JSON esperado."""
    transcricao = anonimizar(transcricao)
    chaves = ", ".join(f'"{k}"' for k in CAMPOS)
    return (
        "Transcricao da consulta (cada linha: [horario] texto):\n\n"
        f"{transcricao}\n\n"
        "Extraia as informacoes para um prontuario e responda APENAS com um JSON "
        f"com exatamente estas chaves: {chaves}.\n"
        "Cada valor deve ser um texto (string). Use \"Nao relatado\" quando faltar dado."
    )


# Modelos Gemini em ordem de preferência: testa o primeiro, cai para o próximo se falhar.
MODELOS_GEMINI = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def _build_json_schema(keys: list[str], strict: bool = True) -> dict:
    """Monta um JSON Schema com as chaves dadas, todas como string obrigatória.

    strict=False omite additionalProperties (necessário para Gemini).
    """
    schema: dict = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in keys},
        "required": keys,
    }
    if strict:
        schema["additionalProperties"] = False
    return schema


def _detectar_provedor() -> str:
    """Retorna o primeiro provedor com key configurada (Gemini > OpenAI > Anthropic)."""
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "Nenhuma chave de API encontrada. Configure ao menos uma no .env:\n"
        "  GEMINI_API_KEY, OPENAI_API_KEY ou ANTHROPIC_API_KEY"
    )


def _chamar_llm_raw(
    provedor: str,
    sistema: str,
    usuario: str,
    progresso=print,
    schema_keys: list[str] | None = None,
) -> dict:
    """Chamada de baixo nível ao LLM com prompts customizados.

    schema_keys: quando fornecido, ativa Structured Outputs para garantir
    que a resposta siga exatamente o schema JSON com essas chaves.
    """
    if provedor == "gemini":
        import google.generativeai as genai  # noqa: PLC0415
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        gen_config = {"response_mime_type": "application/json", "temperature": 0}
        if schema_keys:
            gen_config["response_schema"] = _build_json_schema(schema_keys, strict=False)
        ultimo_erro = None
        for nome_modelo in MODELOS_GEMINI:
            try:
                modelo = genai.GenerativeModel(
                    nome_modelo,
                    system_instruction=sistema,
                    generation_config=gen_config,
                )
                t0 = time.monotonic()
                resposta = modelo.generate_content(usuario)
                duracao = time.monotonic() - t0
                uso = resposta.usage_metadata
                t_in, t_out = uso.prompt_token_count, uso.candidates_token_count
                progresso(
                    f"LLM {nome_modelo}: {duracao:.2f}s | "
                    f"entrada={t_in} tok, saída={t_out} tok, {t_out / duracao:.1f} tok/s"
                )
                return json.loads(resposta.text)
            except json.JSONDecodeError as erro:
                raise ValueError(f"Gemini ({nome_modelo}) nao devolveu JSON valido. Resposta:\n{resposta.text}") from erro
            except Exception as erro:
                ultimo_erro = erro
                continue
        raise RuntimeError(f"Erro na API do Gemini (todos os modelos falharam): {ultimo_erro}")

    elif provedor == "openai":
        from openai import OpenAI  # noqa: PLC0415
        cliente = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if schema_keys:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "prontuario",
                    "strict": True,
                    "schema": _build_json_schema(schema_keys),
                },
            }
        else:
            response_format = {"type": "json_object"}
        try:
            t0 = time.monotonic()
            resposta = cliente.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                response_format=response_format,
                temperature=0,
            )
            duracao = time.monotonic() - t0
            uso = resposta.usage
            progresso(
                f"LLM gpt-4o-mini: {duracao:.2f}s | "
                f"entrada={uso.prompt_tokens} tok, saída={uso.completion_tokens} tok, "
                f"{uso.completion_tokens / duracao:.1f} tok/s"
            )
            return json.loads(resposta.choices[0].message.content)
        except json.JSONDecodeError as erro:
            conteudo = resposta.choices[0].message.content if resposta else ""
            raise ValueError(f"OpenAI nao devolveu JSON valido. Resposta:\n{conteudo}") from erro
        except Exception as erro:
            raise RuntimeError(f"Erro na API da OpenAI: {erro}") from erro

    else:  # anthropic
        import anthropic  # noqa: PLC0415
        cliente = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        try:
            t0 = time.monotonic()
            kwargs: dict = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2048,
                "temperature": 0,
                "system": sistema,
                "messages": [{"role": "user", "content": usuario}],
            }
            if schema_keys:
                kwargs["tools"] = [{
                    "name": "preencher_prontuario",
                    "description": "Preenche os campos do prontuário médico com base na transcrição",
                    "input_schema": _build_json_schema(schema_keys),
                }]
                kwargs["tool_choice"] = {"type": "tool", "name": "preencher_prontuario"}
            mensagem = cliente.messages.create(**kwargs)
            duracao = time.monotonic() - t0
            uso = mensagem.usage
            progresso(
                f"LLM claude-haiku: {duracao:.2f}s | "
                f"entrada={uso.input_tokens} tok, saída={uso.output_tokens} tok, "
                f"{uso.output_tokens / duracao:.1f} tok/s"
            )
            if schema_keys:
                for bloco in mensagem.content:
                    if bloco.type == "tool_use" and bloco.name == "preencher_prontuario":
                        return bloco.input
                raise ValueError("Anthropic nao retornou chamada de ferramenta valida.")
            conteudo = mensagem.content[0].text
            inicio = conteudo.find("{")
            fim = conteudo.rfind("}") + 1
            if inicio == -1 or fim == 0:
                raise ValueError(f"Anthropic nao devolveu JSON valido. Resposta:\n{conteudo}")
            return json.loads(conteudo[inicio:fim])
        except (ValueError, json.JSONDecodeError):
            raise
        except Exception as erro:
            raise RuntimeError(f"Erro na API da Anthropic: {erro}") from erro


def estruturar_transcricao(transcricao: str, progresso=print) -> dict:
    """Pipeline de estruturacao: transcricao -> dict de campos do prontuario (CLI)."""
    provedor = _detectar_provedor()
    progresso(f"Estruturando a consulta em campos de prontuario (via {provedor})...")
    schema_keys = list(CAMPOS.keys())
    campos = _chamar_llm_raw(
        provedor, PROMPT_SISTEMA, montar_prompt_usuario(transcricao),
        progresso=progresso, schema_keys=schema_keys,
    )
    return {k: campos.get(k, "Nao relatado") for k in CAMPOS}


def gerar_texto_legivel(campos: dict) -> str:
    """Monta a versao em texto, pronta para leitura e copia."""
    linhas = []
    for chave, rotulo in CAMPOS.items():
        valor = str(campos.get(chave, "Nao relatado")).strip() or "Nao relatado"
        linhas.append(f"{rotulo}:\n{valor}\n")
    return "\n".join(linhas)


def gerar_template_preenchido(template: str, campos: dict) -> str:
    """Reconstroi o template com os valores preenchidos pelo LLM."""
    linhas = []
    for linha in template.splitlines():
        linhas.append(linha)
        linha_limpa = linha.strip()
        if linha_limpa.endswith(":") and len(linha_limpa) > 1:
            chave = linha_limpa[:-1]
            valor = str(campos.get(chave, "")).strip()
            if valor:
                linhas.append(valor)
    return "\n".join(linhas)


def _parsear_secoes_template(template: str) -> list[str]:
    """Extrai nomes de secoes de linhas terminadas com ':'."""
    secoes = []
    for linha in template.splitlines():
        linha = linha.strip()
        if linha.endswith(":") and len(linha) > 1:
            secoes.append(linha[:-1])
    return secoes


def estruturar_com_template(transcricao: str, template: str, progresso=print) -> dict:
    """Estrutura a transcricao usando as secoes do template como campos do prontuario."""
    secoes = _parsear_secoes_template(template)
    if not secoes:
        raise ValueError("Template nao contem secoes validas (linhas terminando com ':')")

    provedor = _detectar_provedor()
    progresso(f"Estruturando com {len(secoes)} secoes via {provedor}...")

    secoes_json = ", ".join(f'"{s}"' for s in secoes)
    secoes_formatadas = "\n".join(f"- {s}" for s in secoes)
    transcricao_anonima = anonimizar(transcricao)

    prompt_usuario = (
        f"Preencha as seções do prontuário listadas abaixo com base EXCLUSIVAMENTE "
        f"no que foi verbalizado na transcrição. Use \"Não relatado\" para seções sem "
        f"informação explícita. Retorne SOMENTE um JSON com exatamente estas chaves: "
        f"{{{secoes_json}}}.\n\n"
        f"SEÇÕES:\n{secoes_formatadas}\n\n"
        f"TRANSCRIÇÃO:\n{transcricao_anonima}"
    )

    return _chamar_llm_raw(
        provedor, PROMPT_SISTEMA, prompt_usuario,
        progresso=progresso, schema_keys=secoes,
    )


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
    except (RuntimeError, ValueError) as erro:
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
