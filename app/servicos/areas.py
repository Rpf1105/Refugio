"""Serviço de domínio para Áreas Afetadas.

Expõe operações de CRUD e consulta sobre a entidade ``area_afetada``,
isolando o acesso ao banco: cada função recebe uma conexão SQLite
(``sqlite3.Connection``) aberta pela camada de API, que é responsável por
gerenciar seu ciclo de vida (abertura, commit externo e fechamento).

Referências:
- Cadastro de Área Afetada pelo Órgão Responsável (R6.1 — registra limites
  geográficos/``poligono`` e o Nível_de_Gravidade).
- Listagem das Áreas Afetadas do Município selecionado (R1.1), incluindo o
  Nível_de_Gravidade (R1.2) e a Cor_de_Gravidade associada (R12.1–R12.3).

O ``poligono`` é persistido como uma string JSON — uma lista de pares
``[lat, lng]`` — e serializado/desserializado por este módulo. O controle de
acesso por perfil (R6.4) é tratado em módulo separado e NÃO é aplicado aqui.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Sequence

from app.dominio.cores import cor_por_nivel


def _serializar_poligono(poligono: Sequence[Sequence[float]]) -> str:
    """Serializa o polígono (lista de ``[lat, lng]``) em uma string JSON.

    Normaliza cada vértice para uma lista de dois ``float`` antes de gravar,
    de modo que a representação persistida seja estável.
    """
    vertices = [[float(lat), float(lng)] for lat, lng in poligono]
    return json.dumps(vertices)


def _desserializar_poligono(poligono_json: str) -> List[List[float]]:
    """Desserializa a string JSON do polígono em uma lista de ``[lat, lng]``."""
    return [[float(lat), float(lng)] for lat, lng in json.loads(poligono_json)]


def criar_area(
    conexao: sqlite3.Connection,
    municipio_id: int,
    descricao: str,
    nivel_gravidade: str,
    poligono: Sequence[Sequence[float]],
) -> int:
    """Cadastra uma Área Afetada e retorna o seu ``id`` (R6.1).

    Registra os limites geográficos (``poligono``, serializado como JSON) e o
    Nível_de_Gravidade da Área Afetada para o Município informado. O valor de
    ``nivel_gravidade`` é validado contra as cores de gravidade conhecidas
    ('baixo', 'medio', 'alto'); um nível inválido levanta ``ValueError``.

    :param conexao: Conexão SQLite aberta (o chamador gerencia seu ciclo de vida).
    :param municipio_id: Identificador do Município ao qual a Área pertence.
    :param descricao: Descrição textual da Área Afetada.
    :param nivel_gravidade: Nível_de_Gravidade ('baixo', 'medio' ou 'alto').
    :param poligono: Limites geográficos como lista de pares ``[lat, lng]``.
    :returns: O ``id`` autoincremental da Área Afetada criada.
    :raises ValueError: se ``nivel_gravidade`` não for um nível válido.
    """
    # Valida o nível antecipadamente (reaproveita a validação do domínio de cores).
    cor_por_nivel(nivel_gravidade)

    cursor = conexao.execute(
        """
        INSERT INTO area_afetada (municipio_id, descricao, nivel_gravidade, poligono)
        VALUES (?, ?, ?, ?)
        """,
        (municipio_id, descricao, nivel_gravidade, _serializar_poligono(poligono)),
    )
    conexao.commit()
    return int(cursor.lastrowid)


def listar_areas(conexao: sqlite3.Connection, municipio_id: int) -> List[Dict[str, Any]]:
    """Lista as Áreas Afetadas cadastradas para um Município (R1.1).

    Cada Área retornada inclui o Nível_de_Gravidade (R1.2) e a Cor_de_Gravidade
    correspondente (R12.1–R12.3), com o ``poligono`` já desserializado em uma
    lista de pares ``[lat, lng]``.

    Quando o Município não possui Áreas Afetadas, retorna uma lista vazia — a
    mensagem de ausência (R1.3) é responsabilidade da camada de apresentação.

    :param conexao: Conexão SQLite aberta.
    :param municipio_id: Identificador do Município cujas Áreas serão listadas.
    :returns: Lista de dicionários, um por Área Afetada, ordenada por ``id``.
    """
    linhas = conexao.execute(
        """
        SELECT id, municipio_id, descricao, nivel_gravidade, poligono, atualizado_em
        FROM area_afetada
        WHERE municipio_id = ?
        ORDER BY id
        """,
        (municipio_id,),
    ).fetchall()

    return [
        {
            "id": linha["id"],
            "municipio_id": linha["municipio_id"],
            "descricao": linha["descricao"],
            "nivel_gravidade": linha["nivel_gravidade"],
            "cor": cor_por_nivel(linha["nivel_gravidade"]),
            "poligono": _desserializar_poligono(linha["poligono"]),
            "atualizado_em": linha["atualizado_em"],
        }
        for linha in linhas
    ]
