"""Camada de acesso a dados do Aplicativo Refúgio (SQLite em arquivo).

Este módulo isola todo o acesso ao banco do restante do sistema (R8.1 — camada
de dados isolada). Expõe:

- :func:`conectar` — abre uma conexão SQLite (com ``row_factory`` e chaves
  estrangeiras habilitadas);
- :func:`inicializar_banco` — cria o schema (idempotente) e semeia os dados
  iniciais (Município padrão "Ribeirão Preto" e usuários de exemplo);
- :func:`criar_schema` / :func:`semear_dados_iniciais` — passos individuais,
  úteis em testes.

O caminho do arquivo do banco é configurável via :mod:`app.config`
(``CAMINHO_BANCO``, padrão ``/data/refugio.db``). Testes podem passar um caminho
próprio (por exemplo, um arquivo temporário ou ``":memory:"``).

Modelo de dados: ver a seção *Data Models* do ``design.md``. As métricas de
Gravidade Média/Veracidade dos Incidentes são **derivadas** dos Relatos
associados e, por isso, não são colunas da tabela ``incidente``.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from app import config

# Centro geográfico aproximado de Ribeirão Preto/SP (R7.1).
RIBEIRAO_PRETO_LAT = -21.1775
RIBEIRAO_PRETO_LNG = -47.8103


def _garantir_diretorio(caminho: str) -> None:
    """Cria o diretório pai do arquivo de banco, se necessário.

    Ignorado para bancos em memória (``":memory:"``) e quando o caminho não
    possui diretório pai (arquivo no diretório corrente).
    """
    if caminho == ":memory:":
        return
    diretorio = os.path.dirname(os.path.abspath(caminho))
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)


def conectar(caminho: Optional[str] = None) -> sqlite3.Connection:
    """Abre uma conexão SQLite com o banco do Refúgio.

    :param caminho: Caminho do arquivo de banco. Quando ``None``, usa
        ``config.CAMINHO_BANCO`` (padrão ``/data/refugio.db``).
    :returns: Conexão com ``row_factory = sqlite3.Row`` e ``PRAGMA
        foreign_keys = ON``.
    """
    destino = caminho if caminho is not None else config.CAMINHO_BANCO
    _garantir_diretorio(destino)
    conexao = sqlite3.connect(destino)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


# Instruções DDL do schema. Cada entidade corresponde à seção Data Models do
# design. Identificadores inteiros autoincrementais, exceto onde indicado.
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS municipio (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        nome       TEXT    NOT NULL,
        centro_lat REAL    NOT NULL,
        centro_lng REAL    NOT NULL,
        padrao     INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usuario (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        nome   TEXT    NOT NULL,
        perfil TEXT    NOT NULL CHECK (perfil IN ('cidadao', 'orgao_responsavel'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS area_afetada (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio_id    INTEGER NOT NULL,
        descricao       TEXT    NOT NULL,
        nivel_gravidade TEXT    NOT NULL CHECK (nivel_gravidade IN ('baixo', 'medio', 'alto')),
        poligono        TEXT    NOT NULL,
        atualizado_em   TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (municipio_id) REFERENCES municipio (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS abrigo (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio_id INTEGER NOT NULL,
        nome         TEXT    NOT NULL,
        endereco     TEXT    NOT NULL,
        lat          REAL    NOT NULL,
        lng          REAL    NOT NULL,
        capacidade   INTEGER,
        FOREIGN KEY (municipio_id) REFERENCES municipio (id)
    )
    """,
    # A tabela incidente é criada antes de relato porque relato referencia
    # incidente_id. O conceito de Incidente_Externo reaproveita esta tabela via
    # as colunas origem/id_externo/gravidade_externa (R15.4).
    """
    CREATE TABLE IF NOT EXISTS incidente (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio_id     INTEGER NOT NULL,
        tipo             TEXT    NOT NULL,
        centro_lat       REAL    NOT NULL,
        centro_lng       REAL    NOT NULL,
        origem           TEXT    NOT NULL DEFAULT 'local'
                             CHECK (origem IN ('local', 'portal_dados_abertos')),
        id_externo       TEXT,
        gravidade_externa REAL,
        criado_em        TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (municipio_id) REFERENCES municipio (id),
        -- Idempotência da importação (R15.5): reimportar o mesmo incidente da
        -- mesma fonte não cria duplicata. A importação usa upsert por esta chave.
        UNIQUE (origem, id_externo)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS relato (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio_id    INTEGER NOT NULL,
        incidente_id    INTEGER,
        usuario_id      INTEGER NOT NULL,
        descricao       TEXT    NOT NULL,
        nivel_gravidade TEXT    NOT NULL CHECK (nivel_gravidade IN ('baixo', 'medio', 'alto')),
        foto_path       TEXT    NOT NULL,
        lat             REAL,
        lng             REAL,
        validado        INTEGER NOT NULL DEFAULT 0,
        criado_em       TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (municipio_id) REFERENCES municipio (id),
        FOREIGN KEY (incidente_id) REFERENCES incidente (id),
        FOREIGN KEY (usuario_id) REFERENCES usuario (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pedido_ajuda (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio_id INTEGER NOT NULL,
        usuario_id   INTEGER NOT NULL,
        descricao    TEXT    NOT NULL,
        lat          REAL,
        lng          REAL,
        criado_em    TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (municipio_id) REFERENCES municipio (id),
        FOREIGN KEY (usuario_id) REFERENCES usuario (id)
    )
    """,
]


def criar_schema(conexao: sqlite3.Connection) -> None:
    """Cria todas as tabelas do schema (idempotente via ``IF NOT EXISTS``)."""
    for ddl in _DDL:
        conexao.execute(ddl)
    conexao.commit()


def semear_dados_iniciais(conexao: sqlite3.Connection) -> None:
    """Semeia o Município padrão e os usuários de exemplo (idempotente).

    - Município "Ribeirão Preto" com ``padrao = 1`` e centro geográfico (R7.1).
    - Usuários de exemplo com perfis ``cidadao`` e ``orgao_responsavel`` (R6.4).

    A operação é idempotente: só insere quando os dados ainda não existem, de
    modo que reinicializações não criem duplicatas.
    """
    # Município padrão (Ribeirão Preto). Garante uma única linha com padrao = 1.
    linha = conexao.execute(
        "SELECT id FROM municipio WHERE nome = ? AND padrao = 1",
        ("Ribeirão Preto",),
    ).fetchone()
    if linha is None:
        conexao.execute(
            """
            INSERT INTO municipio (nome, centro_lat, centro_lng, padrao)
            VALUES (?, ?, ?, 1)
            """,
            ("Ribeirão Preto", RIBEIRAO_PRETO_LAT, RIBEIRAO_PRETO_LNG),
        )

    # Usuários de exemplo (um por perfil). Só insere se o perfil ainda não existir.
    usuarios_exemplo = [
        ("Cidadão Exemplo", "cidadao"),
        ("Órgão Responsável Exemplo", "orgao_responsavel"),
    ]
    for nome, perfil in usuarios_exemplo:
        existe = conexao.execute(
            "SELECT 1 FROM usuario WHERE perfil = ? LIMIT 1",
            (perfil,),
        ).fetchone()
        if existe is None:
            conexao.execute(
                "INSERT INTO usuario (nome, perfil) VALUES (?, ?)",
                (nome, perfil),
            )

    conexao.commit()


def inicializar_banco(caminho: Optional[str] = None) -> sqlite3.Connection:
    """Inicializa o banco: abre conexão, cria o schema e semeia os dados.

    Projetado para ser chamado no startup da aplicação. É idempotente e pode ser
    executado em toda inicialização com segurança.

    :param caminho: Caminho do arquivo de banco. Quando ``None``, usa
        ``config.CAMINHO_BANCO``.
    :returns: A conexão aberta (o chamador é responsável por fechá-la).
    """
    conexao = conectar(caminho)
    criar_schema(conexao)
    semear_dados_iniciais(conexao)
    return conexao
