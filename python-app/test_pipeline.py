#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste de integração do pipeline completo.

Sobe o servidor, chama POST /consulta com audio + template,
mede tempos e verifica se os arquivos foram salvos corretamente.

Uso:
    python test_pipeline.py
"""

import json
import os
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(BASE_DIR, "audios", "consulta_teste.wav")
TEMPLATE = os.path.join(BASE_DIR, "templates", "topicos_pronto_atendimento.txt")
URL_BASE = "http://127.0.0.1:8001"
API_USER = os.getenv("API_USER", "")
API_PASSWORD = os.getenv("API_PASSWORD", "")


def aguardar_servidor(url: str, timeout: int = 30) -> bool:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        try:
            requests.get(url + "/docs", timeout=2)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)
    return False


def separador(titulo: str = ""):
    linha = "=" * 60
    print(f"\n{linha}")
    if titulo:
        print(f"  {titulo}")
        print(linha)


def verificar(condicao: bool, descricao: str):
    status = "PASSOU" if condicao else "FALHOU"
    simbolo = "✓" if condicao else "✗"
    print(f"  {simbolo} [{status}] {descricao}")
    return condicao


def main() -> int:
    falhas = 0

    separador("TESTE DE INTEGRAÇÃO — Pipeline Completo")

    # Pré-condições
    separador("Verificando pré-condições")
    ok_audio = verificar(os.path.isfile(AUDIO), f"Áudio encontrado: {AUDIO}")
    ok_template = verificar(os.path.isfile(TEMPLATE), f"Template encontrado: {TEMPLATE}")
    if not ok_audio or not ok_template:
        print("\n[ERRO] Arquivos de entrada ausentes. Abortando.")
        return 1

    # Inicia servidor
    separador("Subindo servidor (porta 8001)")
    venv_python = os.path.join(BASE_DIR, ".venv312", "bin", "python")
    python_bin = venv_python if os.path.isfile(venv_python) else sys.executable
    proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "api:app", "--port", "8001", "--log-level", "warning"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        print("  Aguardando servidor ficar pronto...")
        t0 = time.monotonic()
        pronto = aguardar_servidor(URL_BASE, timeout=30)
        t_boot = time.monotonic() - t0
        falhas += not verificar(pronto, f"Servidor pronto em {t_boot:.1f}s")
        if not pronto:
            print("\n[ERRO] Servidor não respondeu. Abortando.")
            return 1
        print(f"  Boot em {t_boot:.1f}s")

        # Chamada à API
        separador("Chamando POST /consulta")
        t_req_inicio = time.monotonic()
        with open(AUDIO, "rb") as f_audio, open(TEMPLATE, "rb") as f_template:
            resp = requests.post(
                f"{URL_BASE}/consulta",
                files={
                    "audio": ("consulta_teste.wav", f_audio, "audio/wav"),
                    "template": ("topicos_pronto_atendimento.txt", f_template, "text/plain"),
                },
                auth=(API_USER, API_PASSWORD),
                timeout=300,
            )
        t_req_total = time.monotonic() - t_req_inicio

        falhas += not verificar(resp.status_code == 201, f"HTTP 201 (recebido: {resp.status_code})")
        if resp.status_code != 201:
            print(f"\n  Resposta: {resp.text[:500]}")
            return 1

        dados = resp.json()

        # Validação da resposta
        separador("Validando resposta JSON")
        falhas += not verificar("id" in dados, "Campo 'id' presente")
        falhas += not verificar("transcricao" in dados and len(dados["transcricao"]) > 0, "Transcrição não vazia")
        falhas += not verificar("prontuario" in dados and isinstance(dados["prontuario"], dict), "Prontuário é dict")
        falhas += not verificar("timing" in dados, "Timing presente na resposta")

        # Timing
        separador("Métricas de tempo")
        timing = dados.get("timing", {})
        print(f"  Transcrição (Whisper): {timing.get('transcricao_s', '?')}s")
        print(f"  Estruturação (LLM):    {timing.get('estruturacao_s', '?')}s")
        print(f"  Total no servidor:     {timing.get('total_s', '?')}s")
        print(f"  Tempo total (cliente): {t_req_total:.2f}s")

        # Arquivos salvos
        separador("Verificando arquivos salvos")
        consulta_id = dados.get("id", "")
        dir_transcricoes = os.path.join(BASE_DIR, "transcricoes")
        dir_prontuarios = os.path.join(BASE_DIR, "prontuarios")
        arq_transcricao = os.path.join(dir_transcricoes, f"{consulta_id}.txt")
        arq_prontuario_json = os.path.join(dir_prontuarios, f"{consulta_id}.json")
        arq_prontuario_txt = os.path.join(dir_prontuarios, f"{consulta_id}.txt")

        falhas += not verificar(os.path.isfile(arq_transcricao), f"transcricoes/{consulta_id}.txt")
        falhas += not verificar(os.path.isfile(arq_prontuario_json), f"prontuarios/{consulta_id}.json")
        falhas += not verificar(os.path.isfile(arq_prontuario_txt), f"prontuarios/{consulta_id}.txt")

        # Conteúdo dos arquivos
        if os.path.isfile(arq_prontuario_json):
            with open(arq_prontuario_json, encoding="utf-8") as f:
                prontuario_salvo = json.load(f)
            falhas += not verificar(
                prontuario_salvo == dados["prontuario"],
                "JSON salvo bate com a resposta da API",
            )

        if os.path.isfile(arq_prontuario_txt):
            with open(arq_prontuario_txt, encoding="utf-8") as f:
                txt_salvo = f.read()
            falhas += not verificar(len(txt_salvo) > 0, "Template preenchido (.txt) não está vazio")

        # GET /consulta/{id}
        separador("Testando GET /consulta/{id}")
        resp_get = requests.get(
            f"{URL_BASE}/consulta/{consulta_id}",
            auth=(API_USER, API_PASSWORD),
            timeout=10,
        )
        falhas += not verificar(resp_get.status_code == 200, f"GET /consulta/{consulta_id} → HTTP 200")
        if resp_get.status_code == 200:
            dados_get = resp_get.json()
            falhas += not verificar("template_preenchido" in dados_get, "Campo 'template_preenchido' presente")
            falhas += not verificar(len(dados_get.get("template_preenchido", "")) > 0, "template_preenchido não vazio")
            falhas += not verificar(dados_get.get("prontuario") == dados["prontuario"], "Prontuário GET bate com POST")

        resp_404 = requests.get(
            f"{URL_BASE}/consulta/id-inexistente",
            auth=(API_USER, API_PASSWORD),
            timeout=10,
        )
        falhas += not verificar(resp_404.status_code == 404, "GET com id inválido → HTTP 404")

        # Preview do prontuário
        separador("Prontuário gerado")
        if os.path.isfile(arq_prontuario_txt):
            with open(arq_prontuario_txt, encoding="utf-8") as f:
                print(f.read())

    finally:
        proc.terminate()
        proc.wait(timeout=5)

    separador("Resultado final")
    if falhas == 0:
        print("  Todos os testes PASSARAM.\n")
        return 0
    else:
        print(f"  {falhas} teste(s) FALHARAM.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
