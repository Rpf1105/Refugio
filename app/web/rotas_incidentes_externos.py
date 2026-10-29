"""Endpoints da API de Incidentes_Externos e sincronização manual (tarefa 10.6).

Este módulo expõe um :class:`fastapi.APIRouter` autocontido (``router``) com os
endpoints ligados à Sincronização_de_Dados_Abertos (R15.3, R15.4), prontos para
serem incluídos na aplicação por ``app.include_router(router)`` na fiação final
(tarefa 14.1). O roteador reutiliza o adaptador de integração já implementado
(:mod:`app.integracao.dados_abertos`) e o Controle de Acesso por perfil
(:mod:`app.servicos.acesso`) — não reimplementa busca, importação nem regras de
autorização.

Endpoints:

- ``GET /api/incidentes-externos`` — lista os Incidentes_Externos de um
  Município (os de ``origem = "portal_dados_abertos"``), diferenciando a
  procedência no retorno (campos ``origem`` e ``fonte``) e derivando a
  Cor_de_Gravidade a partir da ``gravidade_externa`` quando informada (R15.3,
  R15.4). Assume o Município padrão quando ``municipio_id`` é omitido (R7.1).
- ``POST /api/admin/sincronizar-dados-abertos`` — dispara manualmente a
  Sincronização_de_Dados_Abertos para um Município; operação de gestão restrita
  ao Órgão_Responsável via cabeçalho ``X-Perfil`` (R6.4). Útil para a demo, pois
  permite acionar sob demanda o fluxo periódico (R15.1–R15.6) e devolve os
  campos de :class:`~app.integracao.dados_abertos.ResultadoSincronizacao`.

Procedência e cor dos Incidentes_Externos
------------------------------------------

A ``gravidade_externa`` vinda da fonte é opcional e não tem escala garantida.
O design pede que a cor seja aplicada "quando informada"; adota-se aqui a
convenção do domínio (``cor_por_media`` espera gravidade média em ``[1.0, 3.0]``):

- quando ``gravidade_externa`` está presente **e** cai em ``[1.0, 3.0]``, a cor é
  derivada por :func:`app.dominio.cores.cor_por_media` (mesma faixa dos
  Incidentes locais, R12.4), para que a leitura visual seja coerente;
- quando ``gravidade_externa`` é ausente (``None``) **ou** fora de ``[1.0, 3.0]``,
  usa-se a **cor neutra distinta** :data:`COR_NEUTRA_EXTERNA` (``#6B7A8F`` —
  um azul-acinzentado), que não coincide com nenhuma Cor_de_Gravidade (amarelo
  ``#F2C94C`` / laranja ``#E8A028`` / vermelho ``#C9291C``). Essa escolha
  sinaliza no retorno que o incidente tem procedência externa e gravidade não
  classificável, reforçando a diferenciação de origem exigida por R15.3.

A conexão SQLite por requisição vem da dependência :func:`app.main.get_conn`
(reutilizada, não reimplementada). As exceções de acesso (``ErroAcesso``)
propagam para o *exception handler* global de :mod:`app.main` (HTTP 403).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, Query

from app.dominio.cores import cor_por_media
from app.integracao.dados_abertos import ORIGEM, sincronizar
from app.main import get_conn
from app.servicos.acesso import (
    CABECALHO_PERFIL,
    exigir_orgao_responsavel,
    resolver_perfil,
)

# Rótulo de procedência exibido para diferenciar dos Relatos/Incidentes locais
# no retorno da API e no Mapa (R15.3).
FONTE_DADOS_ABERTOS = "Portal de Dados Abertos"

# Cor neutra/distinta usada quando a gravidade_externa é ausente ou está fora da
# faixa classificável [1.0, 3.0]. Azul-acinzentado que não colide com nenhuma
# Cor_de_Gravidade do Sistema de Design, sinalizando procedência externa (R15.3).
COR_NEUTRA_EXTERNA = "#6B7A8F"

router = APIRouter(prefix="/api", tags=["incidentes-externos", "dados-abertos"])


def _municipio_padrao_id(conn: sqlite3.Connection) -> int:
    """Retorna o ``id`` do Município padrão (Ribeirão Preto, R7.1).

    Usado quando a consulta/sincronização não informa ``municipio_id``,
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


def _cor_incidente_externo(gravidade_externa: Optional[float]) -> str:
    """Deriva a Cor_de_Gravidade de um Incidente_Externo (R15.3, R12.4).

    Aplica :func:`app.dominio.cores.cor_por_media` quando ``gravidade_externa``
    está presente e dentro de ``[1.0, 3.0]``; caso contrário, devolve a cor
    neutra :data:`COR_NEUTRA_EXTERNA`, que sinaliza procedência externa sem
    gravidade classificável.

    :param gravidade_externa: Gravidade informada pela fonte (pode ser ``None``).
    :returns: A cor (hex string) a usar para o incidente no Mapa.
    """
    if gravidade_externa is None:
        return COR_NEUTRA_EXTERNA
    if 1.0 <= gravidade_externa <= 3.0:
        return cor_por_media(gravidade_externa)
    return COR_NEUTRA_EXTERNA


def _serializar_incidente_externo(incidente: sqlite3.Row) -> Dict[str, Any]:
    """Converte a linha de Incidente_Externo nos campos exibidos no Mapa (R15.3).

    Expõe o identificador externo, o tipo, as coordenadas do centro, a gravidade
    informada pela fonte e a Cor_de_Gravidade derivada, além dos marcadores de
    procedência (``origem`` técnica e ``fonte`` legível) que diferenciam o
    incidente dos Relatos/Incidentes locais (R15.3, R15.4).

    :param incidente: Linha de Incidente (``sqlite3.Row``) com ``origem`` externa.
    :returns: Dicionário serializável com os campos do Incidente_Externo.
    """
    gravidade_externa = incidente["gravidade_externa"]
    return {
        "id": incidente["id"],
        "municipio_id": incidente["municipio_id"],
        "id_externo": incidente["id_externo"],
        "tipo": incidente["tipo"],
        "centro_lat": incidente["centro_lat"],
        "centro_lng": incidente["centro_lng"],
        "gravidade_externa": gravidade_externa,
        "cor": _cor_incidente_externo(gravidade_externa),
        "origem": incidente["origem"],
        "fonte": FONTE_DADOS_ABERTOS,
        "criado_em": incidente["criado_em"],
    }


@router.get("/incidentes-externos")
def obter_incidentes_externos(
    municipio_id: Optional[int] = Query(
        default=None,
        description="Município cujos Incidentes_Externos serão listados.",
    ),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Lista os Incidentes_Externos do Município (R15.3, R15.4).

    Consulta os incidentes com ``origem = "portal_dados_abertos"`` do Município
    alvo, diferenciando a procedência no retorno (``origem`` + ``fonte``) e
    derivando a Cor_de_Gravidade da ``gravidade_externa`` quando informada
    (cor neutra quando ausente/fora da faixa — ver :data:`COR_NEUTRA_EXTERNA`).
    Assume o Município padrão quando ``municipio_id`` é omitido (R7.1).

    :returns: ``{ "municipio_id": ..., "fonte": ..., "incidentes_externos": [...] }``.
    """
    alvo_municipio = (
        municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    )

    linhas = conn.execute(
        """
        SELECT id, municipio_id, tipo, centro_lat, centro_lng,
               origem, id_externo, gravidade_externa, criado_em
        FROM incidente
        WHERE origem = ? AND municipio_id = ?
        ORDER BY id
        """,
        (ORIGEM, alvo_municipio),
    ).fetchall()

    return {
        "municipio_id": alvo_municipio,
        "fonte": FONTE_DADOS_ABERTOS,
        "incidentes_externos": [_serializar_incidente_externo(l) for l in linhas],
    }


@router.post("/admin/sincronizar-dados-abertos")
def sincronizar_dados_abertos(
    municipio_id: Optional[int] = Query(
        default=None,
        description="Município alvo da sincronização (padrão: Município padrão).",
    ),
    x_perfil: Optional[str] = Header(default=None, alias=CABECALHO_PERFIL),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """Dispara manualmente a Sincronização_de_Dados_Abertos — restrito ao Órgão.

    Operação de gestão: resolve o perfil a partir do cabeçalho ``X-Perfil`` e
    exige o perfil de Órgão_Responsável (``exigir_orgao_responsavel`` levanta
    ``ErroAcesso`` → HTTP 403 quando negado, R6.4). Em seguida aciona
    :func:`app.integracao.dados_abertos.sincronizar` para o Município alvo
    (padrão quando omitido, R7.1), que busca e importa os incidentes com
    degradação graciosa em caso de falha (R15.6). Útil para a demo, pois permite
    acionar sob demanda o fluxo normalmente periódico (R15.1–R15.6).

    :returns: ``{ "municipio_id": ..., "sucesso": bool, "importados": int,
        "erro": str | None }`` — os campos de ``ResultadoSincronizacao``.
    """
    perfil = resolver_perfil(x_perfil)
    exigir_orgao_responsavel(perfil)

    alvo_municipio = (
        municipio_id if municipio_id is not None else _municipio_padrao_id(conn)
    )

    resultado = sincronizar(conn, alvo_municipio)

    return {
        "municipio_id": alvo_municipio,
        "sucesso": resultado.sucesso,
        "importados": resultado.importados,
        "erro": resultado.erro,
    }
