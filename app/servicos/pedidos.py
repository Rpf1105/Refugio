"""Serviço de Pedidos de Ajuda (R11).

Orquestra a criação e a consulta de Pedidos de Ajuda sobre a camada de dados
(SQLite). As regras de domínio são reutilizadas das funções puras:

- validação de descrição obrigatória via :func:`app.dominio.validacao.validar_pedido`
  (R11.1, R11.2);
- aplicação do Filtro de Conteúdo via
  :func:`app.dominio.filtro_conteudo.contem_termo_bloqueado` (R11.3–R11.5).

Quando a descrição contém um Termo Bloqueado, o serviço sinaliza a rejeição com
a mesma exceção de validação do domínio
(:class:`app.dominio.validacao.ErroValidacao`), de modo que a camada de API a
converta na resposta JSON padronizada ``{ "erro", "campo" }`` com status 400
(R11.5).

Todo o acesso ao banco é feito pela conexão SQLite recebida como parâmetro
(``conn``), mantendo o serviço independente da origem/ciclo de vida da conexão
e do caminho do arquivo (R8.1 — camada de dados isolada).
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.dominio.filtro_conteudo import contem_termo_bloqueado
from app.dominio.validacao import CAMPO_DESCRICAO, ErroValidacao, validar_pedido

# Mensagem exibida ao Cidadão quando o Filtro de Conteúdo detecta um Termo
# Bloqueado na descrição do Pedido de Ajuda (R11.5).
MSG_FILTRO_CONTEUDO = (
    "solicitações de pagamento não são permitidas por motivo de segurança"
)


def criar_pedido(
    conn: sqlite3.Connection,
    municipio_id: int,
    usuario_id: int,
    descricao: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> sqlite3.Row:
    """Cria e persiste um Pedido de Ajuda, aplicando as regras de domínio.

    Ordem de verificação:
        1. Valida a descrição obrigatória (R11.1, R11.2). Descrição vazia ou
           apenas espaços é rejeitada por :func:`validar_pedido`.
        2. Aplica o Filtro de Conteúdo (R11.3–R11.5). Se a descrição contém ao
           menos um Termo Bloqueado, rejeita a publicação com a mensagem
           padronizada (R11.5).
        3. Insere o Pedido de Ajuda associando a localização (``lat``/``lng``) e
           a data e hora da publicação (``criado_em``, preenchido pelo banco com
           ``datetime('now')``) (R11.6).

    Args:
        conn: Conexão SQLite aberta (com ``row_factory = sqlite3.Row``).
        municipio_id: Identificador do Município ao qual o Pedido pertence.
        usuario_id: Identificador do Cidadão que publica o Pedido.
        descricao: Descrição textual da situação informada pelo Cidadão.
        lat: Latitude da localização do Pedido (opcional).
        lng: Longitude da localização do Pedido (opcional).

    Returns:
        A linha (``sqlite3.Row``) do Pedido de Ajuda recém-criado, incluindo
        ``id``, ``descricao``, ``lat``, ``lng`` e ``criado_em``, de modo a
        alimentar a confirmação de publicação exibida ao Cidadão (R11.7).

    Raises:
        ErroValidacao: quando a descrição é inválida (R11.2) ou quando o Filtro
            de Conteúdo detecta um Termo Bloqueado (R11.5); a instância carrega a
            ``mensagem`` e o ``campo`` correspondente.
    """
    # 1. Descrição obrigatória (R11.1, R11.2).
    validar_pedido(descricao)

    # 2. Filtro de Conteúdo (R11.3–R11.5). Reaproveita ErroValidacao para que a
    # API mapeie a rejeição para o erro JSON 400.
    if contem_termo_bloqueado(descricao):
        raise ErroValidacao(MSG_FILTRO_CONTEUDO, campo=CAMPO_DESCRICAO)

    # 3. Persistência com localização e data/hora (R11.6). O criado_em é
    # preenchido pelo DEFAULT (datetime('now')) do schema.
    cursor = conn.execute(
        """
        INSERT INTO pedido_ajuda (municipio_id, usuario_id, descricao, lat, lng)
        VALUES (?, ?, ?, ?, ?)
        """,
        (municipio_id, usuario_id, descricao, lat, lng),
    )
    conn.commit()

    pedido = conn.execute(
        """
        SELECT id, municipio_id, usuario_id, descricao, lat, lng, criado_em
        FROM pedido_ajuda
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return pedido


def listar_pedidos(
    conn: sqlite3.Connection, municipio_id: int
) -> list[sqlite3.Row]:
    """Lista os Pedidos de Ajuda publicados para um Município (R11.8, R11.9).

    A listagem é a mesma para Cidadão e Órgão Responsável: ambos consultam os
    Pedidos de Ajuda do Município selecionado (R11.9 reutiliza R11.8). Os campos
    retornados incluem a descrição textual, a localização geográfica
    (``lat``/``lng``) e a data e hora de cada Pedido (``criado_em``) (R11.8).

    Os Pedidos são ordenados do mais recente para o mais antigo.

    Args:
        conn: Conexão SQLite aberta (com ``row_factory = sqlite3.Row``).
        municipio_id: Identificador do Município cujos Pedidos serão listados.

    Returns:
        Lista de linhas (``sqlite3.Row``) dos Pedidos de Ajuda do Município,
        possivelmente vazia quando não há Pedidos publicados.
    """
    linhas = conn.execute(
        """
        SELECT id, municipio_id, usuario_id, descricao, lat, lng, criado_em
        FROM pedido_ajuda
        WHERE municipio_id = ?
        ORDER BY criado_em DESC, id DESC
        """,
        (municipio_id,),
    ).fetchall()
    return list(linhas)
