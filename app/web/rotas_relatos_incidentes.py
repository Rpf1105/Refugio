"""Endpoints da API de Relatos e Incidentes do Aplicativo Refúgio.

Este módulo expõe um :class:`fastapi.APIRouter` autocontido (``router``) com os
endpoints de Relato e Incidente (tarefa 9.3), prontos para serem incluídos na
aplicação por ``app.include_router(router)`` na fiação final (tarefa 14.1). O
roteador reutiliza os serviços de domínio já implementados — não reimplementa
regras de negócio — e deixa as exceções de domínio propagarem para os
*exception handlers* globais de :mod:`app.main` (``ErroValidacao`` → 400,
``ErroAcesso`` → 403).

Endpoints:

- ``POST /api/relatos`` — recebe ``multipart/form-data`` com os campos do Relato
  e a foto (``UploadFile``), cria o Relato (R4.1–R4.5), associa-o a um Incidente
  por tipo + proximidade (R9.1) e devolve uma confirmação de recebimento com o
  ``id`` do Relato criado (R4.6).
- ``GET /api/relatos`` — lista os Relatos de um Município, com filtro opcional
  por Nível_de_Gravidade (R5.1–R5.3); assume o Município padrão quando
  ``municipio_id`` é omitido (R7.1).
- ``POST /api/relatos/{id}/validar`` — marca um Relato como validado; operação
  de gestão restrita ao Órgão_Responsável via cabeçalho ``X-Perfil`` (R6.3,
  R6.4).
- ``GET /api/incidentes`` — lista os Incidentes locais do Município com
  Gravidade_Média, Cor_de_Gravidade e Veracidade, omitindo Incidentes sem
  Relatos (R9.1, R9.6, R9.7, R9.8, R12.4).

Observações de design:

- A conexão SQLite por requisição vem da dependência :func:`app.main.get_conn`
  (reutilizada, não reimplementada).
- O Nível_de_Gravidade trafega no enum de armazenamento ('baixo', 'medio',
  'alto'); a validação de valores fica a cargo do domínio (R4.4).
- O ``tipo`` de ocorrência é opcional no envio; quando ausente, usa-se o tipo
  padrão :data:`TIPO_PADRAO` ("geral"), de modo que o Relato ainda seja
  agrupável em um Incidente (R9.1). A escolha é deliberada e documentada: o
  protótipo agrupa por tipo + proximidade, e um tipo padrão único evita que
  Relatos sem tipo informado deixem de formar Incidentes.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, Header, Path, Query, UploadFile

from app.main import get_conn
from app.servicos.acesso import (
    CABECALHO_PERFIL,
    exigir_orgao_responsavel,
    resolver_perfil,
)
from app.servicos.incidentes import associar_relato, listar_incidentes
from app.servicos.relatos import (
    criar_relato,
    listar_relatos,
    marcar_relato_validado,
)

# Tipo de ocorrência assumido quando o envio não informa um ``tipo`` explícito.
# Mantém o Relato agrupável em um Incidente por tipo + proximidade (R9.1).
TIPO_PADRAO = "geral"

router = APIRouter(prefix="/api", tags=["relatos", "incidentes"])


def _municipio_padrao_id(conn: sqlite3.Connection) -> int:
    """Retorna o ``id`` do Município padrão (Ribeirão Preto, R7.1).

    Usado quando o Cidadão consulta Relatos sem informar ``municipio_id``,
    assumindo o Município padrão disponibilizado pelo Aplicativo. Recorre ao
    primeiro Município cadastrado caso, por algum motivo, nenhum esteja marcado
    como padrão.

    :param conn: Conexão SQLite aberta.
    :returns: O identificador do Município padrão.
    """
    linha = conn.execute(
        "SELECT id FROM municipio WHERE padrao = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if linha is None:
        linha = conn.execute(
            "SELECT id FROM municipio ORDER BY id LIMIT 1"
        ).fetchone()
    return int(linha["id"])


def _serializar_relato(relato: sqlite3.Row) -> Dict[str, Any]:
    """Converte a linha de Relato nos campos exibidos ao Cidadão (R5.2).

    Expõe descrição, Nível_de_Gravidade, foto, localização, status de validação
    e data/hora, além dos identificadores de associação (Município, Incidente,
    usuário). O ``validado`` é convertido para booleano para a resposta JSON.

    :param relato: Linha de Relato (``sqlite3.Row``).
    :returns: Dicionário serializável com os campos do Relato.
    """
    return {
        "id": relato["id"],
        "municipio_id": relato["municipio_id"],
        "incidente_id": relato["incidente_id"],
        "usuario_id": relato["usuario_id"],
        "descricao": relato["descricao"],
        "nivel_gravidade": relato["nivel_gravidade"],
        "foto_path": relato["foto_path"],
        "lat": relato["lat"],
        "lng": relato["lng"],
        "validado": bool(relato["validado"]),
        "criado_em": relato["criado_em"],
    }


@router.post("/relatos")
async def postar_relato(
    municipio_id: int = Form(..., description="Município ao qual o Relato pertence."),
    usuario_id: int = Form(..., description="Usuário (Cidadão) autor do Relato."),
    descricao: str = Form(..., description="Descrição textual do Relato."),
    nivel_gravidade: str = Form(
        ..., description="Nível de gravidade: 'baixo', 'medio' ou 'alto'."
    ),
    foto: UploadFile = File(..., description="Foto obrigatória do Relato."),
    lat: Optional[float] = Form(default=None, description="Latitude do envio."),
    lng: Optional[float] = Form(default=None, description="Longitude do envio."),
    tipo: Optional[str] = Form(
        default=None,
        description="Tipo da ocorrência (ex.: 'enchente'); padrão 'geral'.",
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Cria um Relato a partir de ``multipart/form-data`` e confirma o recebimento.

    Fluxo:
        1. Lê os bytes da foto enviada (``await foto.read()``) e repassa, junto
           ao nome do arquivo, a :func:`app.servicos.relatos.criar_relato`, que
           valida a entrada (R4.2–R4.4), grava a foto antes de persistir a linha
           (R4.5) e associa localização e data/hora (R4.1, R4.5).
        2. Associa o Relato recém-criado a um Incidente por tipo + proximidade
           via :func:`app.servicos.incidentes.associar_relato` (R9.1), usando o
           ``tipo`` informado ou :data:`TIPO_PADRAO` quando ausente.
        3. Devolve uma confirmação de recebimento com o ``id`` do Relato criado
           e o ``incidente_id`` ao qual foi associado (R4.6).

    As exceções de validação (``ErroValidacao``) propagam para o handler global
    (HTTP 400). Não há captura local — a confirmação só é retornada no sucesso.

    :returns: ``{ "mensagem": ..., "relato": {...}, "incidente_id": ... }``.
    """
    foto_bytes = await foto.read()

    relato = criar_relato(
        conn,
        municipio_id=municipio_id,
        usuario_id=usuario_id,
        descricao=descricao,
        nivel_gravidade=nivel_gravidade,
        foto_bytes=foto_bytes,
        foto_filename=foto.filename,
        lat=lat,
        lng=lng,
    )

    tipo_ocorrencia = (tipo or "").strip() or TIPO_PADRAO
    incidente_id = associar_relato(
        conn,
        relato_id=relato["id"],
        municipio_id=municipio_id,
        tipo=tipo_ocorrencia,
        lat=lat,
        lng=lng,
    )

    # Relê o Relato para refletir o ``incidente_id`` já associado na resposta.
    relato_atualizado = conn.execute(
        """
        SELECT id, municipio_id, incidente_id, usuario_id, descricao,
               nivel_gravidade, foto_path, lat, lng, validado, criado_em
        FROM relato
        WHERE id = ?
        """,
        (relato["id"],),
    ).fetchone()

    return {
        "mensagem": "Relato recebido com sucesso.",
        "relato": _serializar_relato(relato_atualizado),
        "incidente_id": incidente_id,
    }


@router.get("/relatos")
def obter_relatos(
    municipio_id: Optional[int] = Query(
        default=None, description="Município cujos Relatos serão listados."
    ),
    gravidade: Optional[str] = Query(
        default=None,
        description="Filtro opcional por nível: 'baixo', 'medio' ou 'alto'.",
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Lista os Relatos de um Município, opcionalmente filtrados por gravidade.

    Restringe sempre ao Município (R5.1, R7.2) e, quando ``gravidade`` é
    informada, ao Nível_de_Gravidade correspondente (R5.3). Quando
    ``municipio_id`` é omitido, assume o Município padrão (R7.1). Cada Relato
    traz os campos exibidos ao Cidadão (R5.2).

    :returns: ``{ "municipio_id": ..., "gravidade": ..., "relatos": [...] }``.
    """
    alvo_municipio = (
        municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    )

    relatos = listar_relatos(conn, alvo_municipio, gravidade=gravidade)

    return {
        "municipio_id": alvo_municipio,
        "gravidade": gravidade,
        "relatos": [_serializar_relato(r) for r in relatos],
    }


@router.post("/relatos/{relato_id}/validar")
def validar_relato_endpoint(
    relato_id: int = Path(..., description="Identificador do Relato a validar."),
    x_perfil: Optional[str] = Header(default=None, alias=CABECALHO_PERFIL),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Marca um Relato como validado — operação restrita ao Órgão (R6.3, R6.4).

    Resolve o perfil a partir do cabeçalho ``X-Perfil`` e exige o perfil de
    Órgão_Responsável (``exigir_orgao_responsavel`` levanta ``ErroAcesso`` →
    HTTP 403 quando negado, R6.4). Em seguida marca o Relato como validado via
    :func:`app.servicos.relatos.marcar_relato_validado` (R6.3) e devolve o
    Relato atualizado.

    :returns: ``{ "mensagem": ..., "relato": {...} }`` com ``validado = true``.
    """
    perfil = resolver_perfil(x_perfil)
    exigir_orgao_responsavel(perfil)

    relato = marcar_relato_validado(conn, relato_id)

    return {
        "mensagem": "Relato validado com sucesso.",
        "relato": _serializar_relato(relato),
    }


@router.get("/incidentes")
def obter_incidentes(
    municipio_id: Optional[int] = Query(
        default=None, description="Município cujos Incidentes serão listados."
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Lista os Incidentes locais do Município com métricas derivadas.

    Para cada Incidente local com ao menos um Relato associado, devolve a
    Gravidade_Média, a Cor_de_Gravidade e a Veracidade derivadas dos Relatos
    (R9.1, R9.6, R9.7, R12.4); Incidentes sem Relatos são omitidos (R9.8).
    Assume o Município padrão quando ``municipio_id`` é omitido (R7.1).

    :returns: ``{ "municipio_id": ..., "incidentes": [...] }``.
    """
    alvo_municipio = (
        municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    )

    incidentes = listar_incidentes(conn, alvo_municipio)

    return {
        "municipio_id": alvo_municipio,
        "incidentes": incidentes,
    }
