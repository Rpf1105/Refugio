"""Endpoints de Municípios, Áreas Afetadas e Abrigos (tarefa 9.2).

Este módulo expõe um :class:`fastapi.APIRouter` autocontido (``router``) com os
endpoints de consulta e gestão de Municípios, Áreas_Afetadas e Abrigos. É
projetado para ser incluído em ``app.main`` pela tarefa 14.1 via
``app.include_router(router)``, sem que este módulo precise alterar o ``main``.

Responsabilidades e rastreabilidade:

- ``GET /api/municipios`` — lista todos os Municípios cadastrados, base para a
  seleção de Município no frontend (R7.1, R7.3).
- ``GET /api/areas`` — lista as Áreas_Afetadas de um Município, cada uma com o
  Nível_de_Gravidade (R1.2) e a Cor_de_Gravidade associada (R1.1); quando o
  ``municipio_id`` é omitido, usa o Município padrão (R7.1). Sem Áreas, retorna
  uma mensagem de ausência para o frontend (R1.3).
- ``POST /api/areas`` — cadastra uma Área_Afetada; operação de gestão restrita
  ao Órgão_Responsável (R6.1, R6.4).
- ``GET /api/abrigos`` — lista os Abrigos de um Município (R2.1) com nome,
  endereço e capacidade (R2.2); quando ``lat``/``lng`` são informados, inclui a
  distância Cidadão → Abrigo (R2.4). Sem Abrigos, retorna uma mensagem de
  ausência (R2.3).
- ``POST /api/abrigos`` — cadastra um Abrigo; operação de gestão restrita ao
  Órgão_Responsável (R6.2, R6.4).

O perfil do usuário é lido do cabeçalho HTTP ``X-Perfil`` (constante
``CABECALHO_PERFIL``), resolvido por :func:`resolver_perfil` e exigido como
Órgão_Responsável por :func:`exigir_orgao_responsavel`, que levanta
``ErroAcesso`` (convertido em HTTP 403 pelos handlers de ``app.main``).

Convenção de ausência de dados (R1.3, R2.3): os endpoints de listagem sempre
retornam o corpo ``{ "<entidade>": [...], "mensagem": <str | None> }``. A chave
``mensagem`` é ``None`` quando há dados e recebe a frase de ausência quando a
lista está vazia, permitindo ao frontend decidir a exibição sem inspecionar o
tamanho da lista.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header

from app.main import AbrigoCriar, AreaCriar, get_conn
from app.servicos.abrigos import criar_abrigo, listar_abrigos
from app.servicos.acesso import (
    CABECALHO_PERFIL,
    exigir_orgao_responsavel,
    resolver_perfil,
)
from app.servicos.areas import criar_area, listar_areas

# Frases de ausência de dados usadas pelo frontend (R1.3, R2.3).
MSG_SEM_AREAS = "não há Áreas Afetadas cadastradas"
MSG_SEM_ABRIGOS = "não há Abrigos cadastrados"

router = APIRouter(prefix="/api", tags=["municipios-areas-abrigos"])


def _municipio_padrao_id(conexao: sqlite3.Connection) -> int:
    """Retorna o ``id`` do Município padrão (``padrao = 1``), semeado no startup.

    Serve de valor padrão para as consultas que omitem ``municipio_id`` (R7.1).
    Quando, por alguma razão, nenhum Município padrão existe, recorre ao primeiro
    Município por ``id`` como degradação graciosa.

    :param conexao: Conexão SQLite aberta.
    :returns: O ``id`` do Município padrão (ou do primeiro cadastrado).
    :raises ValueError: se não houver nenhum Município cadastrado.
    """
    linha = conexao.execute(
        "SELECT id FROM municipio WHERE padrao = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    if linha is None:
        linha = conexao.execute(
            "SELECT id FROM municipio ORDER BY id LIMIT 1"
        ).fetchone()
    if linha is None:
        raise ValueError("nenhum Município cadastrado")
    return int(linha["id"])


@router.get("/municipios")
def get_municipios(conn: sqlite3.Connection = Depends(get_conn)) -> Dict[str, Any]:
    """Lista todos os Municípios cadastrados (R7.1, R7.3).

    Base para o seletor de Município do frontend. Cada Município inclui ``id``,
    ``nome``, o centro geográfico (``centro_lat``/``centro_lng``) e o indicador
    ``padrao`` (``True`` para o Município padrão, "Ribeirão Preto").

    :param conn: Conexão SQLite injetada por :func:`app.main.get_conn`.
    :returns: ``{ "municipios": [ { id, nome, centro_lat, centro_lng, padrao } ] }``.
    """
    linhas = conn.execute(
        """
        SELECT id, nome, centro_lat, centro_lng, padrao
        FROM municipio
        ORDER BY id
        """
    ).fetchall()

    municipios = [
        {
            "id": linha["id"],
            "nome": linha["nome"],
            "centro_lat": linha["centro_lat"],
            "centro_lng": linha["centro_lng"],
            "padrao": bool(linha["padrao"]),
        }
        for linha in linhas
    ]
    return {"municipios": municipios}


@router.get("/areas")
def get_areas(
    municipio_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Lista as Áreas_Afetadas de um Município (R1.1).

    Cada Área inclui o Nível_de_Gravidade (R1.2) e a Cor_de_Gravidade associada
    (R1.1), além do polígono já desserializado. Quando ``municipio_id`` é
    omitido, usa o Município padrão (R7.1).

    Quando não há Áreas cadastradas, retorna a lista vazia e a ``mensagem`` de
    ausência (R1.3); com dados, ``mensagem`` é ``None``.

    :param municipio_id: Município cujas Áreas serão listadas (opcional; padrão
        é o Município padrão).
    :param conn: Conexão SQLite injetada por :func:`app.main.get_conn`.
    :returns: ``{ "areas": [...], "mensagem": <str | None> }``.
    """
    alvo = municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    areas = listar_areas(conn, alvo)
    mensagem = None if areas else MSG_SEM_AREAS
    return {"areas": areas, "mensagem": mensagem}


@router.post("/areas", status_code=201)
def post_areas(
    corpo: AreaCriar,
    conn: sqlite3.Connection = Depends(get_conn),
    x_perfil: Optional[str] = Header(default=None, alias=CABECALHO_PERFIL),
) -> Dict[str, Any]:
    """Cadastra uma Área_Afetada (R6.1); restrito ao Órgão_Responsável (R6.4).

    Resolve o perfil do cabeçalho ``X-Perfil`` e exige o perfil de
    Órgão_Responsável antes de persistir. Caso contrário, ``ErroAcesso`` é
    levantado e convertido em HTTP 403 pelos handlers de ``app.main``.

    :param corpo: Dados da Área (:class:`app.main.AreaCriar`).
    :param conn: Conexão SQLite injetada por :func:`app.main.get_conn`.
    :param x_perfil: Valor do cabeçalho ``X-Perfil`` (perfil do usuário).
    :returns: ``{ "id": <id da Área criada> }``.
    """
    exigir_orgao_responsavel(resolver_perfil(x_perfil))
    area_id = criar_area(
        conn,
        corpo.municipio_id,
        corpo.descricao,
        corpo.nivel_gravidade,
        corpo.poligono,
    )
    return {"id": area_id}


@router.get("/abrigos")
def get_abrigos(
    municipio_id: Optional[int] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Lista os Abrigos de um Município (R2.1) com nome, endereço e capacidade (R2.2).

    Quando a localização do Cidadão é informada (``lat`` e ``lng`` ambos
    presentes), cada Abrigo inclui ``distancia_metros``, a distância Cidadão →
    Abrigo (R2.4), e a lista é ordenada do mais próximo ao mais distante. Quando
    ``municipio_id`` é omitido, usa o Município padrão (R7.1).

    Sem Abrigos cadastrados, retorna a lista vazia e a ``mensagem`` de ausência
    (R2.3); com dados, ``mensagem`` é ``None``.

    :param municipio_id: Município cujos Abrigos serão listados (opcional; padrão
        é o Município padrão).
    :param lat: Latitude do Cidadão em graus (opcional).
    :param lng: Longitude do Cidadão em graus (opcional).
    :param conn: Conexão SQLite injetada por :func:`app.main.get_conn`.
    :returns: ``{ "abrigos": [...], "mensagem": <str | None> }``.
    """
    alvo = municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    abrigos: List[Dict[str, Any]] = listar_abrigos(conn, alvo, lat=lat, lng=lng)
    mensagem = None if abrigos else MSG_SEM_ABRIGOS
    return {"abrigos": abrigos, "mensagem": mensagem}


@router.post("/abrigos", status_code=201)
def post_abrigos(
    corpo: AbrigoCriar,
    conn: sqlite3.Connection = Depends(get_conn),
    x_perfil: Optional[str] = Header(default=None, alias=CABECALHO_PERFIL),
) -> Dict[str, Any]:
    """Cadastra um Abrigo (R6.2); restrito ao Órgão_Responsável (R6.4).

    Resolve o perfil do cabeçalho ``X-Perfil`` e exige o perfil de
    Órgão_Responsável antes de persistir. Caso contrário, ``ErroAcesso`` é
    levantado e convertido em HTTP 403 pelos handlers de ``app.main``.

    :param corpo: Dados do Abrigo (:class:`app.main.AbrigoCriar`).
    :param conn: Conexão SQLite injetada por :func:`app.main.get_conn`.
    :param x_perfil: Valor do cabeçalho ``X-Perfil`` (perfil do usuário).
    :returns: ``{ "id": <id do Abrigo criado> }``.
    """
    exigir_orgao_responsavel(resolver_perfil(x_perfil))
    abrigo_id = criar_abrigo(
        conn,
        corpo.municipio_id,
        corpo.nome,
        corpo.endereco,
        corpo.lat,
        corpo.lng,
        corpo.capacidade,
    )
    return {"id": abrigo_id}
