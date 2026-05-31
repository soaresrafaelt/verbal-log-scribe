#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI — pipeline completo de consulta médica.

POST /consulta
  - Recebe: arquivo de áudio + template de prontuário
  - Executa: transcrição (Whisper) → correção (difflib/glossário) → estruturação (LLM)
  - Persiste: transcricoes/<id>.txt e prontuarios/<id>.json
  - Retorna: {id, transcricao, prontuario}

GET /consulta/{id}
  - Recebe: id da consulta
  - Retorna: {id, criado_em, transcricao, prontuario, template_preenchido, timing}
"""

import json
import os
import secrets
import sqlite3
import tempfile
import time
from datetime import datetime

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials

load_dotenv()

from estruturar import DIR_PRONTUARIOS, estruturar_com_template, gerar_template_preenchido
from transcrever import DIR_TRANSCRICOES, caminho_roteiro, gerar_roteiro_do_audio

app = FastAPI(title="Verbal Log Scribe API")
security = HTTPBasic()

_API_USER = os.getenv("API_USER", "")
_API_PASSWORD = os.getenv("API_PASSWORD", "")

# Configuração do banco de dados SQLite
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "consultas.db")


def _init_db():
    """Inicializa o banco de dados SQLite com a tabela de consultas."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consultas (
                id TEXT PRIMARY KEY,
                criado_em TEXT NOT NULL,
                transcricao TEXT NOT NULL,
                prontuario TEXT NOT NULL,
                template_preenchido TEXT NOT NULL,
                timing TEXT NOT NULL
            )
        """)
        conn.commit()


_init_db()


def verificar_credenciais(credentials: HTTPBasicCredentials = Depends(security)):
    usuario_ok = secrets.compare_digest(credentials.username.encode(), _API_USER.encode())
    senha_ok = secrets.compare_digest(credentials.password.encode(), _API_PASSWORD.encode())
    if not (usuario_ok and senha_ok):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _gerar_id() -> str:
    """Gera ID único baseado em timestamp com sufixo aleatório."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + secrets.token_hex(2)


@app.post("/consulta", status_code=201)
async def consulta(
    audio: UploadFile,
    template: UploadFile,
    _: str = Depends(verificar_credenciais),
):
    template_str = (await template.read()).decode("utf-8")
    audio_bytes = await audio.read()

    # Validação de arquivo de áudio
    EXTENSOES_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    ext_audio = os.path.splitext(audio.filename or "")[1].lower()
    if ext_audio not in EXTENSOES_AUDIO:
        raise HTTPException(status_code=422, detail=f"Formato de áudio não suportado: '{ext_audio}'. Use: {', '.join(sorted(EXTENSOES_AUDIO))}")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Arquivo de áudio está vazio.")
    if not template_str.strip():
        raise HTTPException(status_code=422, detail="Template está vazio.")

    consulta_id = _gerar_id()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    t_inicio = time.monotonic()
    try:
        tmp.write(audio_bytes)
        tmp.close()

        t0 = time.monotonic()
        try:
            transcricao = gerar_roteiro_do_audio(tmp.name)
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            raise HTTPException(status_code=422, detail=str(e))
        t_transcricao = time.monotonic() - t0

        t0 = time.monotonic()
        try:
            prontuario = estruturar_com_template(transcricao, template_str)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        t_estruturacao = time.monotonic() - t0

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")
    finally:
        os.unlink(tmp.name)

    os.makedirs(DIR_TRANSCRICOES, exist_ok=True)
    with open(caminho_roteiro(consulta_id), "w", encoding="utf-8") as f:
        f.write(transcricao + "\n")

    os.makedirs(DIR_PRONTUARIOS, exist_ok=True)
    caminho_json = os.path.join(DIR_PRONTUARIOS, f"{consulta_id}.json")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(prontuario, f, ensure_ascii=False, indent=2)

    caminho_txt = os.path.join(DIR_PRONTUARIOS, f"{consulta_id}.txt")
    with open(caminho_txt, "w", encoding="utf-8") as f:
        f.write(gerar_template_preenchido(template_str, prontuario) + "\n")

    timing = {
        "transcricao_s": round(t_transcricao, 2),
        "estruturacao_s": round(t_estruturacao, 2),
        "total_s": round(time.monotonic() - t_inicio, 2),
    }

    # Persiste consulta no banco de dados SQLite
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO consultas VALUES (?, ?, ?, ?, ?, ?)",
            (
                consulta_id,
                datetime.now().isoformat(),
                transcricao,
                json.dumps(prontuario, ensure_ascii=False),
                gerar_template_preenchido(template_str, prontuario),
                json.dumps(timing, ensure_ascii=False),
            ),
        )
        conn.commit()

    return {"id": consulta_id, "transcricao": transcricao, "prontuario": prontuario, "timing": timing}


@app.get("/consulta/{consulta_id}")
def buscar_consulta(
    consulta_id: str,
    _: str = Depends(verificar_credenciais),
):
    """Retorna uma consulta já processada pelo seu ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM consultas WHERE id = ?", (consulta_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Consulta '{consulta_id}' não encontrada.")
    return {
        "id": row["id"],
        "criado_em": row["criado_em"],
        "transcricao": row["transcricao"],
        "prontuario": json.loads(row["prontuario"]),
        "template_preenchido": row["template_preenchido"],
        "timing": json.loads(row["timing"]),
    }
