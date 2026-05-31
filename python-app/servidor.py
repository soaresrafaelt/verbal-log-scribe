#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel local da POC: servidor HTTP minimo (so biblioteca padrao) que liga as
tres etapas numa unica interface web com abas:

    1. Gravar audio   -> envia o .wav para esta maquina (POST /api/upload)
    2. Transcrever     -> roda faster-whisper + pyannote (transcrever.py)
    3. Estruturar      -> roda o LLM local via Ollama (estruturar.py)

PRIVACIDADE (LGPD): o servidor escuta SOMENTE em 127.0.0.1 (localhost). Nada e
exposto na rede; nenhum audio ou transcricao sai desta maquina. Sem Flask/etc:
usamos http.server para nao adicionar dependencias nem peso.

Uso:
    python servidor.py            # abre em http://127.0.0.1:8000
    python servidor.py 9000       # porta alternativa
"""

import glob
import json
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import estruturar
import glossario
import transcrever

# -------------------------------------------------------------------------
# Configuracoes
# -------------------------------------------------------------------------
HOST = "127.0.0.1"          # NUNCA expor na rede: dados clinicos sao locais (LGPD)
PORTA_PADRAO = 8000
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
PAGINA = os.path.join(DIR_BASE, "painel.html")

# Organizacao por etapa: cada consulta tem um "slug" (identificador unico) e seus
# arquivos sao nomeados por ele em cada pasta -> o historico acumula, nada e
# sobrescrito. No painel o slug e o horario do upload; no CLI e o nome do audio.
#   audios/<slug>.wav  ->  transcricoes/<slug>.txt  ->  prontuarios/<slug>.{json,txt}
# As pastas do roteiro/prontuario vem dos modulos transcrever/estruturar (DRY).
DIR_AUDIOS = os.path.join(DIR_BASE, "audios")


def caminho_audio(slug: str) -> str:
    """Caminho do audio de uma consulta: audios/<slug>.wav."""
    return os.path.join(DIR_AUDIOS, f"{slug}.wav")


def novo_slug() -> str:
    """Gera um slug de consulta a partir do horario atual (ordenavel e legivel)."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def listar_consultas() -> list:
    """Varre as tres pastas e devolve as consultas (mais recente primeiro).

    Cada item: {slug, tem_audio, tem_roteiro, tem_prontuario, atualizado}.
    Ordena pelo arquivo mais recente do slug (mtime), entao a ultima trabalhada
    aparece no topo, misturando consultas do painel e do CLI sem conflito.
    """
    info = {}  # slug -> dict acumulado

    def registrar(caminho: str, chave: str) -> None:
        slug = os.path.splitext(os.path.basename(caminho))[0]
        item = info.setdefault(slug, {
            "slug": slug, "tem_audio": False, "tem_roteiro": False,
            "tem_prontuario": False, "atualizado": 0.0,
        })
        item[chave] = True
        item["atualizado"] = max(item["atualizado"], os.path.getmtime(caminho))

    for caminho in glob.glob(os.path.join(DIR_AUDIOS, "*.wav")):
        registrar(caminho, "tem_audio")
    for caminho in glob.glob(os.path.join(transcrever.DIR_TRANSCRICOES, "*.txt")):
        registrar(caminho, "tem_roteiro")
    for caminho in glob.glob(os.path.join(estruturar.DIR_PRONTUARIOS, "*.json")):
        registrar(caminho, "tem_prontuario")

    return sorted(info.values(), key=lambda i: i["atualizado"], reverse=True)


def consulta_mais_recente() -> str | None:
    """Slug da consulta trabalhada por ultimo (para reabrir o painel onde parou)."""
    consultas = listar_consultas()
    return consultas[0]["slug"] if consultas else None


# -------------------------------------------------------------------------
# Estado do trabalho em andamento (uma tarefa por vez)
# -------------------------------------------------------------------------
# O pipeline leva minutos; roda numa thread de fundo e o painel pergunta o
# progresso por polling em /api/status. 'etapa' e atualizada pelos callbacks.
# 'consulta' e o slug da consulta ativa (sobre quem as tarefas operam).
_lock = threading.Lock()
estado = {
    "rodando": False,   # ha um job em andamento?
    "tarefa": None,     # "transcrever" | "estruturar"
    "etapa": "",        # mensagem de progresso atual (amigavel)
    "erro": None,       # mensagem de erro do ultimo job, se houve
    "concluido": False, # o ultimo job terminou com sucesso?
    "consulta": None,   # slug da consulta ativa
}


def _set_etapa(texto: str) -> None:
    """Callback de progresso passado aos pipelines (transcrever/estruturar)."""
    with _lock:
        estado["etapa"] = str(texto).strip()
    print(f"  [{estado['tarefa']}] {texto}")


def _ler_token() -> str:
    """Le o HF_TOKEN do .env sem encerrar o processo (diferente do CLI)."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DIR_BASE, ".env"))
    token = os.getenv("HF_TOKEN")
    if not token or not token.startswith("hf_"):
        raise RuntimeError(
            "Token do Hugging Face ausente ou invalido. Crie um arquivo '.env' "
            "nesta pasta com a linha: HF_TOKEN=hf_seu_token_aqui"
        )
    return token


# -------------------------------------------------------------------------
# As tarefas em si (rodam dentro da thread de fundo)
# -------------------------------------------------------------------------
def _consulta_ativa() -> str:
    """Slug da consulta ativa; erra se ainda nao ha audio enviado/selecionado."""
    with _lock:
        slug = estado["consulta"]
    if not slug:
        raise RuntimeError("Nenhuma consulta ativa. Grave/envie um audio na aba 'Gravar' primeiro.")
    return slug


def _tarefa_transcrever() -> None:
    slug = _consulta_ativa()
    audio = caminho_audio(slug)
    if not os.path.isfile(audio):
        raise RuntimeError("Audio da consulta nao encontrado. Reenvie pela aba 'Gravar'.")
    token = _ler_token()
    roteiro = transcrever.gerar_roteiro_do_audio(audio, token, progresso=_set_etapa)
    saida = transcrever.caminho_roteiro(slug)
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as arq:
        arq.write(roteiro + "\n")


def _tarefa_estruturar() -> None:
    slug = _consulta_ativa()
    try:
        with open(transcrever.caminho_roteiro(slug), "r", encoding="utf-8") as arq:
            transcricao = arq.read().strip()
    except FileNotFoundError:
        raise RuntimeError("Roteiro ainda nao existe. Rode a aba 'Transcrever' primeiro.")
    if not transcricao:
        raise RuntimeError("O roteiro esta vazio.")

    campos = estruturar.estruturar_transcricao(transcricao, progresso=_set_etapa)
    os.makedirs(estruturar.DIR_PRONTUARIOS, exist_ok=True)
    with open(estruturar.caminho_prontuario(slug, "json"), "w", encoding="utf-8") as arq:
        json.dump(campos, arq, ensure_ascii=False, indent=2)
    with open(estruturar.caminho_prontuario(slug, "txt"), "w", encoding="utf-8") as arq:
        arq.write(estruturar.gerar_texto_legivel(campos))


TAREFAS = {
    "transcrever": _tarefa_transcrever,
    "estruturar": _tarefa_estruturar,
}


def _rodar_em_fundo(nome: str) -> None:
    """Executa a tarefa e atualiza o estado (sucesso ou erro) ao terminar."""
    try:
        TAREFAS[nome]()
        with _lock:
            estado["erro"] = None
            estado["concluido"] = True
            estado["etapa"] = "Concluido."
    except Exception as erro:  # qualquer falha vira mensagem amigavel no painel
        with _lock:
            estado["erro"] = str(erro)
            estado["concluido"] = False
            estado["etapa"] = ""
    finally:
        with _lock:
            estado["rodando"] = False
            estado["tarefa"] = None


def iniciar_tarefa(nome: str) -> bool:
    """Dispara uma tarefa em background. Retorna False se ja ha uma rodando."""
    with _lock:
        if estado["rodando"]:
            return False
        estado.update(rodando=True, tarefa=nome, etapa="Iniciando...",
                      erro=None, concluido=False)
    threading.Thread(target=_rodar_em_fundo, args=(nome,), daemon=True).start()
    return True


# -------------------------------------------------------------------------
# Servidor HTTP
# -------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    # Silencia o log padrao barulhento; mantemos so os prints de progresso.
    def log_message(self, *args):
        pass

    # ---- helpers de resposta ----
    def _json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _texto(self, texto, status=200, tipo="text/plain; charset=utf-8"):
        corpo = texto.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _ler_corpo(self) -> bytes:
        tamanho = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(tamanho) if tamanho else b""

    # ---- GET ----
    def do_GET(self):
        if self.path in ("/", "/index.html", "/painel.html"):
            try:
                with open(PAGINA, "r", encoding="utf-8") as arq:
                    self._texto(arq.read(), tipo="text/html; charset=utf-8")
            except FileNotFoundError:
                self._texto("painel.html nao encontrado.", status=500)
        elif self.path == "/api/status":
            with _lock:
                self._json(dict(estado))
        elif self.path == "/api/consultas":
            with _lock:
                atual = estado["consulta"]
            self._json({"atual": atual, "consultas": listar_consultas()})
        elif self.path == "/api/roteiro":
            slug = self._slug_ativo()
            caminho = transcrever.caminho_roteiro(slug) if slug else None
            self._texto(self._ler_arquivo(caminho) if caminho else "")
        elif self.path == "/api/termos":
            # Categoriza os termos medicos (glossario) presentes no roteiro ativo.
            slug = self._slug_ativo()
            caminho = transcrever.caminho_roteiro(slug) if slug else None
            roteiro = self._ler_arquivo(caminho) if caminho else ""
            self._json({
                "categorias": glossario.categorizar_texto(roteiro),
                "rotulos": glossario.CATEGORIAS_ROTULOS,
            })
        elif self.path == "/api/prontuario":
            slug = self._slug_ativo()
            caminho = estruturar.caminho_prontuario(slug, "json") if slug else None
            conteudo = self._ler_arquivo(caminho) if caminho else ""
            if not conteudo:
                self._json({})
            else:
                self._texto(conteudo, tipo="application/json; charset=utf-8")
        else:
            self._json({"erro": "rota nao encontrada"}, status=404)

    @staticmethod
    def _slug_ativo():
        with _lock:
            return estado["consulta"]

    # ---- POST ----
    def do_POST(self):
        if self.path == "/api/upload":
            dados = self._ler_corpo()
            if not dados:
                return self._json({"erro": "audio vazio"}, status=400)
            # Cada upload inicia uma NOVA consulta (slug = horario) -> historico acumula.
            slug = novo_slug()
            os.makedirs(DIR_AUDIOS, exist_ok=True)
            with open(caminho_audio(slug), "wb") as arq:
                arq.write(dados)
            with _lock:
                estado["consulta"] = slug
            self._json({"ok": True, "bytes": len(dados), "consulta": slug})
        elif self.path in ("/api/transcrever", "/api/estruturar"):
            nome = self.path.rsplit("/", 1)[-1]
            if iniciar_tarefa(nome):
                self._json({"ok": True, "tarefa": nome}, status=202)
            else:
                self._json({"erro": "Ja ha uma tarefa em andamento."}, status=409)
        elif self.path == "/api/consulta":
            # Reabrir uma consulta do historico: define o slug ativo.
            try:
                slug = json.loads(self._ler_corpo() or b"{}").get("consulta")
            except json.JSONDecodeError:
                slug = None
            slugs = {c["slug"] for c in listar_consultas()}
            if not slug or slug not in slugs:
                return self._json({"erro": "Consulta nao encontrada."}, status=404)
            with _lock:
                estado["consulta"] = slug
            self._json({"ok": True, "consulta": slug})
        elif self.path == "/api/roteiro":
            slug = self._slug_ativo()
            if not slug:
                return self._json({"erro": "Nenhuma consulta ativa."}, status=409)
            texto = self._ler_corpo().decode("utf-8")
            caminho = transcrever.caminho_roteiro(slug)
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as arq:
                arq.write(texto)
            self._json({"ok": True})
        else:
            self._json({"erro": "rota nao encontrada"}, status=404)

    @staticmethod
    def _ler_arquivo(caminho: str) -> str:
        try:
            with open(caminho, "r", encoding="utf-8") as arq:
                return arq.read()
        except FileNotFoundError:
            return ""


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORTA_PADRAO
    # Reabre na consulta trabalhada por ultimo (se houver historico).
    estado["consulta"] = consulta_mais_recente()
    servidor = ThreadingHTTPServer((HOST, porta), Handler)
    url = f"http://{HOST}:{porta}"
    print("=" * 60)
    print("Painel da consulta medica (local, offline)")
    print(f"Abra no navegador: {url}")
    print("Tudo roda nesta maquina. Ctrl+C para encerrar.")
    print("=" * 60)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o painel.")
        servidor.shutdown()


if __name__ == "__main__":
    main()
