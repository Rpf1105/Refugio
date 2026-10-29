"""Router da API para Rota Segura e Pedidos de Ajuda (tarefa 9.4).

Este módulo expõe um :class:`fastapi.APIRouter` autocontido com os endpoints de
Rota Segura (R3) e de Pedidos de Ajuda (R11), pensado para ser incluído em
``app.main`` pela tarefa 14.1 via ``app.include_router(router)`` — sem alterar o
``app/main.py``.

Endpoints
---------
- ``GET /api/rotas`` — calcula uma Rota Segura entre origem e destino evitando as
  Áreas Afetadas do Município. As Áreas são recarregadas a cada consulta, de
  modo que a rota seja recalculada conforme o estado atual (R3.4). A rota nunca
  atravessa uma Área Afetada (R3.1, R3.2); quando não há caminho livre, a
  exceção :class:`RotaSeguraNaoEncontradaError` propaga para o handler global,
  que responde 404 com "nenhuma Rota Segura encontrada" (R3.3).
- ``POST /api/pedidos`` — publica um Pedido de Ajuda. A descrição é obrigatória
  (R11.1, R11.2) e passa pelo Filtro de Conteúdo (R11.5); ambos são validados no
  serviço, cujas exceções :class:`ErroValidacao` propagam para o handler global
  (400). Em caso de sucesso, retorna uma confirmação com o Pedido criado
  (R11.6, R11.7).
- ``GET /api/pedidos`` — lista os Pedidos de Ajuda do Município, incluindo
  descrição, localização e data/hora (R11.8, R11.9).

As exceções de domínio (:class:`ErroValidacao`,
:class:`RotaSeguraNaoEncontradaError`) são deixadas propagar para os
*exception handlers* registrados em ``app.main``, que as convertem na resposta
JSON padronizada ``{ "erro", "campo" }`` com os status apropriados.

O Município é opcional nos endpoints de consulta; quando omitido, utiliza-se o
Município padrão semeado no banco ("Ribeirão Preto", ``padrao = 1``).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.dominio.rotas import calcular_rota_segura
from app.dominio.validacao import ErroValidacao
from app.main import PedidoCriar, get_conn
from app.servicos.areas import listar_areas
from app.servicos.pedidos import criar_pedido, listar_pedidos

router = APIRouter()


# ---------------------------------------------------------------------------
# Modelos de resposta
# ---------------------------------------------------------------------------


class RotaResposta(BaseModel):
    """Resposta do cálculo de Rota Segura (``GET /api/rotas``).

    A ``polyline`` é a sequência de pontos ``[[lat, lng], ...]`` da origem ao
    destino, percorrendo apenas regiões fora das Áreas Afetadas (R3.1, R3.2).
    """

    municipio_id: int = Field(..., description="Município considerado no cálculo.")
    origem: list[float] = Field(..., description="Ponto de origem [lat, lng].")
    destino: list[float] = Field(..., description="Ponto de destino [lat, lng].")
    polyline: list[list[float]] = Field(
        ..., description="Pontos da Rota Segura como pares [lat, lng]."
    )


class PedidoResposta(BaseModel):
    """Representação de um Pedido de Ajuda nas respostas da API (R11.7, R11.8)."""

    id: int = Field(..., description="Identificador do Pedido de Ajuda.")
    municipio_id: int = Field(..., description="Município ao qual o Pedido pertence.")
    usuario_id: int = Field(..., description="Usuário que publicou o Pedido.")
    descricao: str = Field(..., description="Descrição informada pelo Cidadão.")
    lat: Optional[float] = Field(default=None, description="Latitude do Pedido.")
    lng: Optional[float] = Field(default=None, description="Longitude do Pedido.")
    criado_em: str = Field(..., description="Data e hora de publicação do Pedido.")


class PedidoConfirmacaoResposta(BaseModel):
    """Confirmação de publicação de um Pedido de Ajuda (R11.6, R11.7).

    Carrega uma mensagem de confirmação para o Cidadão e o Pedido recém-criado.
    """

    confirmado: bool = Field(
        default=True, description="Indica que o Pedido foi publicado com sucesso."
    )
    mensagem: str = Field(..., description="Mensagem de confirmação ao Cidadão.")
    pedido: PedidoResposta = Field(..., description="Pedido de Ajuda publicado.")


# Mensagem de confirmação exibida ao Cidadão após publicar um Pedido (R11.7).
MSG_CONFIRMACAO_PEDIDO = "pedido de ajuda publicado com sucesso"


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _resolver_municipio(conn: sqlite3.Connection, municipio_id: Optional[int]) -> int:
    """Resolve o Município a considerar, usando o padrão quando omitido.

    Quando ``municipio_id`` é informado, ele é usado diretamente. Quando omitido
    (``None``), busca o Município padrão semeado no banco (``padrao = 1``, o
    "Ribeirão Preto" de R7.1).

    Args:
        conn: Conexão SQLite aberta.
        municipio_id: Município informado na requisição, ou ``None``.

    Returns:
        O ``id`` do Município a utilizar.
    """
    if municipio_id is not None:
        return municipio_id
    linha = conn.execute(
        "SELECT id FROM municipio WHERE padrao = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    # Fallback defensivo: primeiro Município cadastrado, se não houver padrão.
    if linha is None:
        linha = conn.execute(
            "SELECT id FROM municipio ORDER BY id LIMIT 1"
        ).fetchone()
    return int(linha["id"])


def _parse_ponto(bruto: str, campo: str) -> list[float]:
    """Converte uma string ``"lat,lng"`` em um ponto ``[lat, lng]`` de floats.

    Aceita espaços ao redor dos valores (ex.: ``"-21.17, -47.81"``). Um formato
    inválido levanta ``ValueError`` com uma mensagem apontando o campo, que o
    chamador converte na resposta de erro apropriada.

    Args:
        bruto: Texto no formato ``"lat,lng"``.
        campo: Nome do parâmetro de origem (para a mensagem de erro).

    Returns:
        O ponto como ``[lat, lng]`` em ``float``.

    Raises:
        ValueError: Quando ``bruto`` não está no formato ``"lat,lng"`` numérico.
    """
    partes = bruto.split(",")
    if len(partes) != 2:
        raise ValueError(f"{campo} deve estar no formato 'lat,lng'")
    try:
        lat = float(partes[0].strip())
        lng = float(partes[1].strip())
    except ValueError as exc:  # valores não numéricos
        raise ValueError(f"{campo} deve conter coordenadas numéricas") from exc
    return [lat, lng]


# ---------------------------------------------------------------------------
# Endpoints — Rota Segura (R3)
# ---------------------------------------------------------------------------


@router.get("/api/rotas", response_model=RotaResposta, tags=["rotas"])
def obter_rota(
    origem: str = Query(
        ..., description="Ponto de origem no formato 'lat,lng'."
    ),
    destino: str = Query(
        ..., description="Ponto de destino no formato 'lat,lng'."
    ),
    municipio_id: Optional[int] = Query(
        default=None,
        description="Município considerado; usa o padrão quando omitido.",
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> RotaResposta:
    """Calcula uma Rota Segura entre origem e destino (R3.1–R3.4).

    Converte ``origem``/``destino`` (strings ``"lat,lng"``) em pontos, recarrega
    as Áreas Afetadas atuais do Município a cada consulta — de modo que a rota
    reflita o estado corrente (recálculo na consulta, R3.4) — e delega o cálculo
    a :func:`app.dominio.rotas.calcular_rota_segura`, que garante que a rota não
    atravessa nenhuma Área Afetada (R3.1, R3.2).

    Quando não existe caminho livre, ``calcular_rota_segura`` levanta
    :class:`RotaSeguraNaoEncontradaError`, que propaga para o handler global e
    resulta em 404 com "nenhuma Rota Segura encontrada" (R3.3).

    Args:
        origem: Ponto de origem no formato ``"lat,lng"``.
        destino: Ponto de destino no formato ``"lat,lng"``.
        municipio_id: Município a considerar; usa o padrão quando omitido.
        conn: Conexão SQLite injetada por :func:`app.main.get_conn`.

    Returns:
        A Rota Segura como :class:`RotaResposta` (origem, destino e polyline).
    """
    # Parse dos pontos; erros de formato viram ErroValidacao (400) via handler.
    try:
        ponto_origem = _parse_ponto(origem, "origem")
    except ValueError as exc:
        raise ErroValidacao(str(exc), campo="origem") from exc
    try:
        ponto_destino = _parse_ponto(destino, "destino")
    except ValueError as exc:
        raise ErroValidacao(str(exc), campo="destino") from exc

    municipio = _resolver_municipio(conn, municipio_id)

    # Recarrega as Áreas Afetadas atuais (recálculo na consulta, R3.4) e extrai
    # os polígonos que delimitam cada uma delas.
    areas = listar_areas(conn, municipio)
    poligonos = [area["poligono"] for area in areas]

    # Deixa RotaSeguraNaoEncontradaError propagar para o handler global (404).
    polyline = calcular_rota_segura(ponto_origem, ponto_destino, poligonos)

    return RotaResposta(
        municipio_id=municipio,
        origem=ponto_origem,
        destino=ponto_destino,
        polyline=polyline,
    )


# ---------------------------------------------------------------------------
# Endpoints — Pedidos de Ajuda (R11)
# ---------------------------------------------------------------------------


def _pedido_para_resposta(linha: Any) -> PedidoResposta:
    """Converte uma linha (``sqlite3.Row``) de Pedido em :class:`PedidoResposta`."""
    return PedidoResposta(
        id=linha["id"],
        municipio_id=linha["municipio_id"],
        usuario_id=linha["usuario_id"],
        descricao=linha["descricao"],
        lat=linha["lat"],
        lng=linha["lng"],
        criado_em=linha["criado_em"],
    )


@router.post(
    "/api/pedidos",
    response_model=PedidoConfirmacaoResposta,
    tags=["pedidos"],
)
def publicar_pedido(
    dados: PedidoCriar,
    conn: sqlite3.Connection = Depends(get_conn),
) -> PedidoConfirmacaoResposta:
    """Publica um Pedido de Ajuda e retorna a confirmação (R11.1–R11.7).

    Delega a :func:`app.servicos.pedidos.criar_pedido`, que valida a descrição
    obrigatória (R11.1, R11.2) e aplica o Filtro de Conteúdo (R11.5). Quando a
    descrição é inválida ou contém um Termo Bloqueado, o serviço levanta
    :class:`ErroValidacao`, que propaga para o handler global (400). Em caso de
    sucesso, associa localização e data/hora (R11.6) e devolve uma confirmação
    com o Pedido criado (R11.7).

    Args:
        dados: Corpo da requisição (:class:`app.main.PedidoCriar`).
        conn: Conexão SQLite injetada por :func:`app.main.get_conn`.

    Returns:
        A confirmação de publicação como :class:`PedidoConfirmacaoResposta`.
    """
    pedido = criar_pedido(
        conn,
        municipio_id=dados.municipio_id,
        usuario_id=dados.usuario_id,
        descricao=dados.descricao,
        lat=dados.lat,
        lng=dados.lng,
    )
    return PedidoConfirmacaoResposta(
        confirmado=True,
        mensagem=MSG_CONFIRMACAO_PEDIDO,
        pedido=_pedido_para_resposta(pedido),
    )


@router.get(
    "/api/pedidos",
    response_model=list[PedidoResposta],
    tags=["pedidos"],
)
def listar_pedidos_endpoint(
    municipio_id: Optional[int] = Query(
        default=None,
        description="Município cujos Pedidos serão listados; usa o padrão quando omitido.",
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[PedidoResposta]:
    """Lista os Pedidos de Ajuda do Município (R11.8, R11.9).

    A listagem é a mesma para Cidadão e Órgão Responsável (R11.9 reutiliza
    R11.8) e inclui a descrição, a localização (``lat``/``lng``) e a data e hora
    (``criado_em``) de cada Pedido. Quando o Município é omitido, usa o padrão.

    Args:
        municipio_id: Município cujos Pedidos serão listados; usa o padrão
            quando omitido.
        conn: Conexão SQLite injetada por :func:`app.main.get_conn`.

    Returns:
        Lista de :class:`PedidoResposta`, do mais recente para o mais antigo.
    """
    municipio = _resolver_municipio(conn, municipio_id)
    linhas = listar_pedidos(conn, municipio)
    return [_pedido_para_resposta(linha) for linha in linhas]
