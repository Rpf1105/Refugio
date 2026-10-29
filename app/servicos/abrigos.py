"""Serviço de domínio para Abrigos.

Expõe operações de CRUD e consulta sobre a entidade ``abrigo``, isolando o
acesso ao banco: cada função recebe uma conexão SQLite (``sqlite3.Connection``)
aberta pela camada de API, que gerencia seu ciclo de vida.

Referências:
- Cadastro de Abrigo pelo Órgão Responsável (R6.2 — registra nome, endereço,
  localização geográfica e capacidade).
- Listagem dos Abrigos do Município selecionado (R2.1), apresentando nome,
  endereço e capacidade (R2.2).
- Cálculo da distância Cidadão → Abrigo via fórmula de Haversine (R2.4), quando
  a localização do Cidadão (``lat``/``lng``) é informada.

O controle de acesso por perfil (R6.4) é tratado em módulo separado e NÃO é
aplicado aqui.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from app.dominio.geo import haversine


def criar_abrigo(
    conexao: sqlite3.Connection,
    municipio_id: int,
    nome: str,
    endereco: str,
    lat: float,
    lng: float,
    capacidade: Optional[int] = None,
) -> int:
    """Cadastra um Abrigo e retorna o seu ``id`` (R6.2).

    Registra o nome, o endereço, a localização geográfica (``lat``/``lng``) e a
    capacidade do Abrigo para o Município informado. A capacidade é opcional
    (coluna anulável no schema).

    :param conexao: Conexão SQLite aberta (o chamador gerencia seu ciclo de vida).
    :param municipio_id: Identificador do Município ao qual o Abrigo pertence.
    :param nome: Nome do Abrigo.
    :param endereco: Endereço textual do Abrigo.
    :param lat: Latitude do Abrigo, em graus decimais.
    :param lng: Longitude do Abrigo, em graus decimais.
    :param capacidade: Capacidade de acolhimento do Abrigo (opcional).
    :returns: O ``id`` autoincremental do Abrigo criado.
    """
    cursor = conexao.execute(
        """
        INSERT INTO abrigo (municipio_id, nome, endereco, lat, lng, capacidade)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (municipio_id, nome, endereco, float(lat), float(lng), capacidade),
    )
    conexao.commit()
    return int(cursor.lastrowid)


def listar_abrigos(
    conexao: sqlite3.Connection,
    municipio_id: int,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Lista os Abrigos cadastrados para um Município (R2.1).

    Cada Abrigo retornado inclui nome, endereço, localização geográfica e
    capacidade (R2.2). Quando a localização do Cidadão é informada (``lat`` e
    ``lng`` ambos não-``None``), cada Abrigo inclui também o campo
    ``distancia_metros``, a distância Cidadão → Abrigo calculada pela fórmula de
    Haversine (R2.4); caso contrário, ``distancia_metros`` é ``None``.

    Quando há distância calculada, a lista é ordenada do Abrigo mais próximo
    para o mais distante; caso contrário, é ordenada por ``id``. Um Município
    sem Abrigos retorna lista vazia — a mensagem de ausência (R2.3) é
    responsabilidade da camada de apresentação.

    :param conexao: Conexão SQLite aberta.
    :param municipio_id: Identificador do Município cujos Abrigos serão listados.
    :param lat: Latitude do Cidadão, em graus decimais (opcional).
    :param lng: Longitude do Cidadão, em graus decimais (opcional).
    :returns: Lista de dicionários, um por Abrigo.
    """
    linhas = conexao.execute(
        """
        SELECT id, municipio_id, nome, endereco, lat, lng, capacidade
        FROM abrigo
        WHERE municipio_id = ?
        ORDER BY id
        """,
        (municipio_id,),
    ).fetchall()

    calcular_distancia = lat is not None and lng is not None

    abrigos: List[Dict[str, Any]] = []
    for linha in linhas:
        distancia = (
            haversine(lat, lng, linha["lat"], linha["lng"])
            if calcular_distancia
            else None
        )
        abrigos.append(
            {
                "id": linha["id"],
                "municipio_id": linha["municipio_id"],
                "nome": linha["nome"],
                "endereco": linha["endereco"],
                "lat": linha["lat"],
                "lng": linha["lng"],
                "capacidade": linha["capacidade"],
                "distancia_metros": distancia,
            }
        )

    # Com a localização do Cidadão, ordena do Abrigo mais próximo ao mais distante.
    if calcular_distancia:
        abrigos.sort(key=lambda abrigo: abrigo["distancia_metros"])

    return abrigos
