"""Serviço de Relatos do Aplicativo Refúgio.

Orquestra o caso de uso de Relato sobre a camada de dados isolada
(:mod:`app.dados.db`) e a validação de domínio (:mod:`app.dominio.validacao`).
Todas as operações recebem uma conexão :class:`sqlite3.Connection` já aberta,
mantendo o acesso ao banco concentrado na camada de dados (R8.1).

Responsabilidades:

- **Criação de Relato** (:func:`criar_relato`): valida descrição, foto e
  Nível_de_Gravidade (R4.2–R4.4); grava a foto em disco **antes** de persistir
  a linha do Relato, garantindo que a linha só exista quando a foto já foi
  salva (R4.5 — ordem importa); associa localização e data/hora do envio
  (R4.1, R4.5).
- **Consulta de Relatos** (:func:`listar_relatos`): filtra por Município
  (R5.1, R7.2) e, opcionalmente, por Nível_de_Gravidade (R5.3), devolvendo os
  campos exibidos ao Cidadão (R5.2).
- **Validação por Órgão** (:func:`marcar_relato_validado`): marca o Relato como
  validado (R6.3).

O diretório de fotos vem da configuração (``config.CAMINHO_FOTOS``, padrão
``/data/fotos``, configurável por variável de ambiente).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app import config
from app.dominio.validacao import ErroValidacao, validar_relato

# Extensão usada quando não é possível inferir uma do nome do arquivo enviado.
_EXTENSAO_PADRAO = ".bin"


def _diretorio_fotos() -> str:
    """Retorna o diretório de armazenamento de fotos (lido da configuração).

    Lê dinamicamente ``config.CAMINHO_FOTOS`` (padrão ``/data/fotos``) a cada
    chamada, de modo que ajustes de configuração em tempo de execução/teste
    sejam respeitados.
    """
    return config.CAMINHO_FOTOS


def _extensao_de(nome_arquivo: Optional[str]) -> str:
    """Extrai a extensão (em minúsculas) do nome do arquivo enviado.

    Cai em :data:`_EXTENSAO_PADRAO` quando o nome é ausente ou não possui
    extensão reconhecível.
    """
    if not nome_arquivo:
        return _EXTENSAO_PADRAO
    _, extensao = os.path.splitext(nome_arquivo)
    return extensao.lower() if extensao else _EXTENSAO_PADRAO


def _salvar_foto(foto_bytes: bytes, foto_filename: Optional[str]) -> str:
    """Grava os bytes da foto em disco com um nome único e devolve o caminho.

    O diretório de destino é criado se necessário. O nome é gerado com
    ``uuid4`` preservando a extensão original, evitando colisões entre envios.

    :returns: O caminho completo do arquivo gravado (armazenado em
        ``relato.foto_path``).
    """
    diretorio = _diretorio_fotos()
    os.makedirs(diretorio, exist_ok=True)
    nome_unico = f"{uuid.uuid4().hex}{_extensao_de(foto_filename)}"
    caminho = os.path.join(diretorio, nome_unico)
    with open(caminho, "wb") as arquivo:
        arquivo.write(foto_bytes)
    return caminho


def _agora_iso() -> str:
    """Data/hora atual (UTC) em ISO 8601, usada como ``criado_em`` (R4.5)."""
    return datetime.now(timezone.utc).isoformat()


def _buscar_relato(conn: sqlite3.Connection, relato_id: int) -> Optional[sqlite3.Row]:
    """Retorna a linha do Relato pelo id, ou ``None`` se não existir."""
    return conn.execute(
        """
        SELECT id, municipio_id, incidente_id, usuario_id, descricao,
               nivel_gravidade, foto_path, lat, lng, validado, criado_em
        FROM relato
        WHERE id = ?
        """,
        (relato_id,),
    ).fetchone()


def criar_relato(
    conn: sqlite3.Connection,
    municipio_id: int,
    usuario_id: int,
    descricao: str,
    nivel_gravidade: str,
    foto_bytes: Optional[bytes],
    foto_filename: Optional[str],
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> sqlite3.Row:
    """Cria e persiste um Relato (R4.1, R4.5).

    Fluxo:
        1. Valida descrição, presença de foto e Nível_de_Gravidade via
           :func:`app.dominio.validacao.validar_relato` (R4.2–R4.4). A presença
           de foto é derivada de ``foto_bytes is not None``.
        2. Grava a foto em disco **primeiro** (:func:`_salvar_foto`).
        3. Só então insere a linha do Relato referenciando ``foto_path``, com a
           data/hora do envio e a localização associadas (R4.5). Assim, nenhuma
           linha de Relato existe sem a foto correspondente já salva.

    :param conn: Conexão SQLite aberta (o acesso ao banco passa por ela).
    :param municipio_id: Município ao qual o Relato pertence.
    :param usuario_id: Autor do Relato (Cidadão).
    :param descricao: Descrição textual do Relato.
    :param nivel_gravidade: 'baixo', 'medio' ou 'alto' (armazenamento).
    :param foto_bytes: Conteúdo binário da foto; ``None`` indica ausência de
        foto (rejeitado pela validação, R4.3).
    :param foto_filename: Nome original do arquivo, usado para inferir a
        extensão do arquivo salvo.
    :param lat: Latitude associada ao Relato (localização do envio).
    :param lng: Longitude associada ao Relato (localização do envio).
    :returns: A linha do Relato recém-criado.
    :raises ErroValidacao: quando a descrição, a foto ou o nível são inválidos.
    """
    # 1) Validação de domínio (R4.2–R4.4). tem_foto deriva de foto_bytes.
    validar_relato(descricao, nivel_gravidade, tem_foto=foto_bytes is not None)

    # 2) Grava a foto ANTES de persistir o Relato (R4.5 — a ordem importa:
    #    o Relato só é persistido após a foto estar salva em disco).
    foto_path = _salvar_foto(foto_bytes, foto_filename)

    # 3) Persiste a linha do Relato referenciando a foto já salva, com
    #    localização e data/hora do envio associadas (R4.1, R4.5).
    criado_em = _agora_iso()
    cursor = conn.execute(
        """
        INSERT INTO relato (
            municipio_id, usuario_id, descricao, nivel_gravidade,
            foto_path, lat, lng, validado, criado_em
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            municipio_id,
            usuario_id,
            descricao,
            nivel_gravidade,
            foto_path,
            lat,
            lng,
            criado_em,
        ),
    )
    conn.commit()

    relato = _buscar_relato(conn, cursor.lastrowid)
    # cursor.lastrowid aponta para a linha recém-inserida; a leitura não deve
    # falhar, mas protegemos a invariante explicitamente.
    assert relato is not None, "Relato recém-inserido não encontrado"
    return relato


def listar_relatos(
    conn: sqlite3.Connection,
    municipio_id: int,
    gravidade: Optional[str] = None,
) -> list[sqlite3.Row]:
    """Lista os Relatos de um Município, opcionalmente filtrados por gravidade.

    Sempre restringe ao ``municipio_id`` informado (R5.1, R7.2). Quando
    ``gravidade`` é informada, restringe adicionalmente ao Nível_de_Gravidade
    correspondente (R5.3). Cada linha traz os campos exibidos ao Cidadão —
    descrição, nível, foto, localização, status de validação e data/hora
    (R5.2).

    :param conn: Conexão SQLite aberta.
    :param municipio_id: Município cujos Relatos devem ser listados.
    :param gravidade: Filtro opcional por Nível_de_Gravidade ('baixo',
        'medio' ou 'alto'). ``None`` retorna todos os Relatos do Município.
    :returns: Lista de linhas de Relato ordenadas do mais recente ao mais
        antigo.
    """
    parametros: list = [municipio_id]
    sql = """
        SELECT id, municipio_id, incidente_id, usuario_id, descricao,
               nivel_gravidade, foto_path, lat, lng, validado, criado_em
        FROM relato
        WHERE municipio_id = ?
    """
    if gravidade is not None:
        sql += " AND nivel_gravidade = ?"
        parametros.append(gravidade)
    sql += " ORDER BY criado_em DESC, id DESC"

    return conn.execute(sql, parametros).fetchall()


def marcar_relato_validado(
    conn: sqlite3.Connection,
    relato_id: int,
) -> sqlite3.Row:
    """Marca um Relato como validado por um Órgão_Responsável (R6.3).

    Define ``validado = 1`` na linha indicada, de modo que a marcação possa ser
    exibida aos Cidadãos. O nome evita colisão com a função de domínio
    ``validar_relato`` (que valida os dados de entrada).

    :param conn: Conexão SQLite aberta.
    :param relato_id: Identificador do Relato a marcar como validado.
    :returns: A linha do Relato atualizada.
    :raises ErroValidacao: quando o Relato não existe (campo ``relato_id``).
    """
    if _buscar_relato(conn, relato_id) is None:
        raise ErroValidacao("relato não encontrado", campo="relato_id")

    conn.execute(
        "UPDATE relato SET validado = 1 WHERE id = ?",
        (relato_id,),
    )
    conn.commit()

    relato = _buscar_relato(conn, relato_id)
    assert relato is not None, "Relato atualizado não encontrado"
    return relato
