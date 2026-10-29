"""Serviço de Incidentes do Aplicativo Refúgio.

Orquestra o caso de uso de Incidente sobre a camada de dados isolada
(:mod:`app.dados.db`), reutilizando as funções puras de domínio de gravidade,
veracidade e cor. Todas as operações recebem uma conexão
:class:`sqlite3.Connection` já aberta, mantendo o acesso ao banco concentrado
na camada de dados (R8.1).

Responsabilidades:

- **Agrupamento de Relatos em Incidentes** (:func:`associar_relato`): associa um
  Relato a um Incidente existente da mesma ocorrência — mesmo ``tipo`` e dentro
  de um raio de proximidade — ou cria um novo Incidente quando nenhum serve
  (R9.1).
- **Consulta de Incidentes** (:func:`listar_incidentes`): para cada Incidente
  **local** com ao menos um Relato associado, deriva a Gravidade_Média, a
  Veracidade e a Cor_de_Gravidade a partir dos Relatos associados (R9.2–R9.6) e
  omite os Incidentes locais sem Relatos (R9.8).

Métricas derivadas (R9.7): a Gravidade_Média, a Veracidade e a cor **não** são
colunas da tabela ``incidente``; são calculadas a partir dos Relatos associados
no momento da leitura. Assim, associar um novo Relato a um Incidente faz com que
a próxima chamada a :func:`listar_incidentes` reflita automaticamente os valores
atualizados, sem necessidade de uma etapa explícita de recálculo.

Observação sobre Incidentes_Externos (``origem = 'portal_dados_abertos'``): são
tratados pela integração de Dados Abertos (tarefa 10.6) e **não** são listados
aqui — :func:`listar_incidentes` restringe a consulta a ``origem = 'local'`` e,
sobre esses, aplica a omissão de R9.8.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, NamedTuple, Optional

from app.dominio.cores import cor_por_media
from app.dominio.geo import haversine
from app.dominio.gravidade import gravidade_media
from app.dominio.veracidade import veracidade

# Origem dos Incidentes criados a partir de Relatos locais (R15.4).
ORIGEM_LOCAL = "local"

# Raio de proximidade, em metros, para considerar que dois Relatos (ou um
# Relato e um Incidente) se referem à mesma ocorrência de emergência (R9.1).
# Mantido simples e explícito: Relatos do mesmo ``tipo`` cujas localizações
# distam até este raio do centro de um Incidente são agrupados nele.
RAIO_PROXIMIDADE_METROS = 500.0


class _RelatoGravidade(NamedTuple):
    """Adaptador mínimo para :func:`gravidade_media`.

    ``gravidade_media`` espera objetos com o atributo ``.nivel_gravidade``.
    ``sqlite3.Row`` suporta acesso por índice/chave, mas não por atributo; por
    isso envolvemos cada linha neste ``NamedTuple`` antes de passar ao domínio.
    """

    nivel_gravidade: str


def _relatos_do_incidente(
    conn: sqlite3.Connection,
    incidente_id: int,
) -> List[sqlite3.Row]:
    """Retorna os Relatos associados a um Incidente (por ``incidente_id``)."""
    return conn.execute(
        """
        SELECT id, nivel_gravidade, lat, lng
        FROM relato
        WHERE incidente_id = ?
        """,
        (incidente_id,),
    ).fetchall()


def associar_relato(
    conn: sqlite3.Connection,
    relato_id: int,
    municipio_id: int,
    tipo: str,
    lat: Optional[float],
    lng: Optional[float],
) -> int:
    """Agrupa um Relato em um Incidente por ``tipo`` + proximidade (R9.1).

    Procura, no mesmo Município e com o mesmo ``tipo`` de ocorrência, um
    Incidente **local** cujo centro esteja dentro de
    :data:`RAIO_PROXIMIDADE_METROS` da localização do Relato. Se encontrar,
    associa o Relato a esse Incidente; caso contrário, cria um novo Incidente
    (origem ``local``) centrado na localização do Relato e associa o Relato a
    ele.

    A proximidade usa a distância de Haversine (:func:`app.dominio.geo.haversine`)
    entre a localização do Relato e o centro do Incidente — uma regra simples e
    determinística, adequada ao protótipo. Quando o Relato não possui
    localização (``lat``/``lng`` ``None``), a proximidade não pode ser avaliada
    e um novo Incidente é sempre criado, usando o centro geográfico do Município
    como centro do Incidente.

    As métricas do Incidente (Gravidade_Média/Veracidade/cor) são derivadas dos
    Relatos associados em tempo de leitura (R9.7); por isso esta associação não
    precisa recalcular nada explicitamente — a próxima consulta já reflete o
    novo Relato.

    :param conn: Conexão SQLite aberta.
    :param relato_id: Identificador do Relato a associar.
    :param municipio_id: Município do Relato (e do Incidente).
    :param tipo: Tipo da ocorrência de emergência (ex.: "enchente", "incendio").
    :param lat: Latitude do Relato (opcional).
    :param lng: Longitude do Relato (opcional).
    :returns: O ``id`` do Incidente ao qual o Relato ficou associado.
    """
    incidente_id = _incidente_proximo(conn, municipio_id, tipo, lat, lng)

    if incidente_id is None:
        incidente_id = _criar_incidente(conn, municipio_id, tipo, lat, lng)

    conn.execute(
        "UPDATE relato SET incidente_id = ? WHERE id = ?",
        (incidente_id, relato_id),
    )
    conn.commit()
    return incidente_id


def _incidente_proximo(
    conn: sqlite3.Connection,
    municipio_id: int,
    tipo: str,
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[int]:
    """Encontra o Incidente local mais próximo do mesmo ``tipo`` (R9.1).

    Retorna o ``id`` do Incidente ``local`` do Município, do mesmo ``tipo``,
    cujo centro esteja dentro de :data:`RAIO_PROXIMIDADE_METROS` e seja o mais
    próximo; ou ``None`` quando não há candidato (inclusive quando o Relato não
    tem localização).
    """
    if lat is None or lng is None:
        return None

    candidatos = conn.execute(
        """
        SELECT id, centro_lat, centro_lng
        FROM incidente
        WHERE municipio_id = ? AND tipo = ? AND origem = ?
        """,
        (municipio_id, tipo, ORIGEM_LOCAL),
    ).fetchall()

    melhor_id: Optional[int] = None
    melhor_distancia = RAIO_PROXIMIDADE_METROS
    for candidato in candidatos:
        distancia = haversine(lat, lng, candidato["centro_lat"], candidato["centro_lng"])
        if distancia <= melhor_distancia:
            melhor_distancia = distancia
            melhor_id = candidato["id"]

    return melhor_id


def _criar_incidente(
    conn: sqlite3.Connection,
    municipio_id: int,
    tipo: str,
    lat: Optional[float],
    lng: Optional[float],
) -> int:
    """Cria um Incidente local e retorna o seu ``id``.

    O centro do Incidente é a localização do Relato quando informada; caso
    contrário, cai no centro geográfico do Município (R7.1), garantindo um
    centro válido mesmo sem localização do Relato.
    """
    centro_lat, centro_lng = lat, lng
    if centro_lat is None or centro_lng is None:
        municipio = conn.execute(
            "SELECT centro_lat, centro_lng FROM municipio WHERE id = ?",
            (municipio_id,),
        ).fetchone()
        if municipio is None:
            raise ValueError(f"município não encontrado: {municipio_id!r}")
        centro_lat, centro_lng = municipio["centro_lat"], municipio["centro_lng"]

    cursor = conn.execute(
        """
        INSERT INTO incidente (municipio_id, tipo, centro_lat, centro_lng, origem)
        VALUES (?, ?, ?, ?, ?)
        """,
        (municipio_id, tipo, float(centro_lat), float(centro_lng), ORIGEM_LOCAL),
    )
    conn.commit()
    return int(cursor.lastrowid)


def listar_incidentes(
    conn: sqlite3.Connection,
    municipio_id: int,
) -> List[Dict[str, Any]]:
    """Lista os Incidentes locais de um Município com métricas derivadas.

    Para cada Incidente de ``origem = 'local'`` do Município que possua ao menos
    um Relato associado, deriva — a partir dos Relatos associados — a
    Gravidade_Média (:func:`app.dominio.gravidade.gravidade_media`), a
    Veracidade (:func:`app.dominio.veracidade.veracidade` sobre a quantidade de
    Relatos) e a Cor_de_Gravidade (:func:`app.dominio.cores.cor_por_media`), além
    de ``qtd_relatos`` (R9.2–R9.6). Incidentes locais **sem** Relatos associados
    são omitidos (R9.8).

    Como as métricas são sempre recalculadas na leitura a partir dos Relatos
    correntes, o resultado reflete automaticamente qualquer Relato associado por
    :func:`associar_relato` (R9.7).

    :param conn: Conexão SQLite aberta.
    :param municipio_id: Município cujos Incidentes devem ser listados.
    :returns: Lista de dicionários, um por Incidente local com Relatos, contendo
        os dados do Incidente mais ``gravidade_media``, ``veracidade``, ``cor``
        e ``qtd_relatos``. Ordenada do Incidente mais recente ao mais antigo.
    """
    incidentes = conn.execute(
        """
        SELECT id, municipio_id, tipo, centro_lat, centro_lng, origem, criado_em
        FROM incidente
        WHERE municipio_id = ? AND origem = ?
        ORDER BY criado_em DESC, id DESC
        """,
        (municipio_id, ORIGEM_LOCAL),
    ).fetchall()

    resultado: List[Dict[str, Any]] = []
    for incidente in incidentes:
        relatos = _relatos_do_incidente(conn, incidente["id"])

        # R9.8: Incidente local sem Relatos associados é omitido da listagem.
        if not relatos:
            continue

        qtd_relatos = len(relatos)
        media = gravidade_media([_RelatoGravidade(r["nivel_gravidade"]) for r in relatos])

        resultado.append(
            {
                "id": incidente["id"],
                "municipio_id": incidente["municipio_id"],
                "tipo": incidente["tipo"],
                "centro_lat": incidente["centro_lat"],
                "centro_lng": incidente["centro_lng"],
                "origem": incidente["origem"],
                "criado_em": incidente["criado_em"],
                "qtd_relatos": qtd_relatos,
                "gravidade_media": media,
                "veracidade": veracidade(qtd_relatos),
                "cor": cor_por_media(media),
            }
        )

    return resultado
