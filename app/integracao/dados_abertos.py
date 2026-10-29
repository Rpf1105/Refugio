"""Adaptador do Portal Brasileiro de Dados Abertos (dados.gov.br) — R15.

Este módulo implementa a **Sincronização_de_Dados_Abertos** (R15.2–R15.6):

- :func:`buscar_incidentes` — requisita os incidentes ao Portal via ``httpx`` e
  os normaliza em uma lista de :class:`IncidenteExterno` (R15.2);
- :func:`importar_incidentes` — importa os Incidentes_Externos de forma
  **idempotente** (upsert pela chave ``(origem, id_externo)``), gravando a
  origem como ``"portal_dados_abertos"`` (R15.3, R15.4, R15.5);
- :func:`sincronizar` — orquestra busca + importação com **degradação graciosa**
  (R15.6): em caso de indisponibilidade, timeout, erro HTTP ou payload inválido,
  preserva os dados existentes, continua operando e registra a falha em log.

Formato de payload esperado
----------------------------

Como o schema real do dataset de incidentes do dados.gov.br varia, definimos
aqui uma **forma normalizada** e fazemos parsing defensivo. O adaptador aceita:

- um objeto JSON com a lista sob a chave ``"incidentes"`` ou ``"data"``; ou
- uma lista JSON de objetos diretamente no corpo da resposta.

Cada incidente é um objeto com (nomes alternativos aceitos entre parênteses)::

    {
        "id_externo":   "<str>",   # (id, codigo, identificador)
        "tipo":         "<str>",   # (categoria, natureza) — padrão "desconhecido"
        "centro_lat":   <float>,   # (lat, latitude)
        "centro_lng":   <float>,   # (lng, lon, longitude)
        "gravidade_externa": <float|null>  # (gravidade, severidade) — opcional
    }

Registros sem ``id_externo`` ou sem coordenadas numéricas válidas são
**descartados** (parsing tolerante), pois não podem ser deduplicados nem
posicionados no Mapa.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app import config

logger = logging.getLogger(__name__)

# Procedência gravada para todo incidente importado desta fonte (R15.4).
ORIGEM = "portal_dados_abertos"

# Timeout padrão (segundos) das requisições ao Portal. Mantido curto para não
# travar a sincronização agendada; em caso de estouro, a degradação graciosa
# (R15.6) assume o controle.
TIMEOUT_PADRAO_SEGUNDOS = 10.0


@dataclass(frozen=True)
class IncidenteExterno:
    """Incidente_Externo normalizado, pronto para importação (R15.3).

    :param id_externo: Identificador do incidente na fonte. Compõe, junto de
        ``origem = "portal_dados_abertos"``, a chave de idempotência (R15.5).
    :param municipio_id: Município ao qual o incidente é associado nos dados do
        Aplicativo.
    :param tipo: Tipo/natureza do incidente (texto livre vindo da fonte).
    :param centro_lat: Latitude do centro do incidente.
    :param centro_lng: Longitude do centro do incidente.
    :param gravidade_externa: Gravidade informada pela fonte (opcional).
    """

    id_externo: str
    municipio_id: int
    tipo: str
    centro_lat: float
    centro_lng: float
    gravidade_externa: Optional[float] = None


class PayloadInvalido(ValueError):
    """Erro de normalização: o corpo recebido do Portal não é interpretável."""


def _extrair_lista(payload: Any) -> list[Any]:
    """Extrai a lista de incidentes do payload, tolerando formatos comuns.

    Aceita uma lista direta, ou um objeto com a lista sob ``"incidentes"`` ou
    ``"data"``. Qualquer outra forma levanta :class:`PayloadInvalido`.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for chave in ("incidentes", "data"):
            valor = payload.get(chave)
            if isinstance(valor, list):
                return valor
    raise PayloadInvalido(
        "payload do Portal não contém uma lista de incidentes reconhecível"
    )


def _primeiro_presente(bruto: dict[str, Any], *chaves: str) -> Any:
    """Retorna o primeiro valor não-``None`` dentre ``chaves`` em ``bruto``."""
    for chave in chaves:
        if chave in bruto and bruto[chave] is not None:
            return bruto[chave]
    return None


def _converter_float(valor: Any) -> Optional[float]:
    """Converte ``valor`` em ``float``, retornando ``None`` se não for possível."""
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _normalizar_item(bruto: Any, municipio_id: int) -> Optional[IncidenteExterno]:
    """Normaliza um item do payload em :class:`IncidenteExterno`.

    Retorna ``None`` (descartando o registro) quando faltam dados essenciais —
    ``id_externo`` ou coordenadas numéricas válidas —, mantendo o parser
    tolerante a registros parciais da fonte.
    """
    if not isinstance(bruto, dict):
        return None

    id_externo = _primeiro_presente(bruto, "id_externo", "id", "codigo", "identificador")
    if id_externo is None or str(id_externo).strip() == "":
        return None

    lat = _converter_float(_primeiro_presente(bruto, "centro_lat", "lat", "latitude"))
    lng = _converter_float(
        _primeiro_presente(bruto, "centro_lng", "lng", "lon", "longitude")
    )
    if lat is None or lng is None:
        return None

    tipo_bruto = _primeiro_presente(bruto, "tipo", "categoria", "natureza")
    tipo = str(tipo_bruto).strip() if tipo_bruto is not None else "desconhecido"
    if tipo == "":
        tipo = "desconhecido"

    gravidade = _converter_float(
        _primeiro_presente(bruto, "gravidade_externa", "gravidade", "severidade")
    )

    return IncidenteExterno(
        id_externo=str(id_externo),
        municipio_id=municipio_id,
        tipo=tipo,
        centro_lat=lat,
        centro_lng=lng,
        gravidade_externa=gravidade,
    )


def normalizar(payload: Any, municipio_id: int) -> list[IncidenteExterno]:
    """Normaliza o payload JSON do Portal em uma lista de Incidentes_Externos.

    Faz parsing defensivo: itens sem identificador ou sem coordenadas válidas
    são descartados. Levanta :class:`PayloadInvalido` apenas quando o formato
    de nível superior é irreconhecível.
    """
    itens = _extrair_lista(payload)
    incidentes: list[IncidenteExterno] = []
    for item in itens:
        incidente = _normalizar_item(item, municipio_id)
        if incidente is not None:
            incidentes.append(incidente)
    return incidentes


def buscar_incidentes(
    municipio: Any,
    cliente: Optional[httpx.Client] = None,
) -> list[IncidenteExterno]:
    """Requisita os incidentes ao Portal e os normaliza (R15.2, R15.3).

    :param municipio: Município alvo. Pode ser o ``id`` (int) ou um objeto/linha
        com atributo/chave ``id`` (ex.: ``sqlite3.Row``), usado para associar os
        Incidentes_Externos ao Município nos dados do Aplicativo.
    :param cliente: Cliente ``httpx.Client`` opcional (injeção para testes).
        Quando ``None``, um cliente é criado e fechado internamente.
    :returns: Lista de :class:`IncidenteExterno` normalizados.
    :raises httpx.HTTPError: Em falha de rede, timeout ou status HTTP de erro.
    :raises PayloadInvalido: Quando o corpo recebido não é interpretável.

    A requisição HTTP e a normalização podem falhar; o tratamento resiliente
    (R15.6) é responsabilidade de :func:`sincronizar`.
    """
    municipio_id = _resolver_municipio_id(municipio)
    url = config.FONTE_DADOSGOVBR_URL

    proprio = cliente is None
    cli = cliente if cliente is not None else httpx.Client(timeout=TIMEOUT_PADRAO_SEGUNDOS)
    try:
        resposta = cli.get(url)
        resposta.raise_for_status()
        try:
            payload = resposta.json()
        except ValueError as exc:  # JSON malformado
            raise PayloadInvalido("resposta do Portal não é um JSON válido") from exc
    finally:
        if proprio:
            cli.close()

    return normalizar(payload, municipio_id)


def importar_incidentes(
    conn: sqlite3.Connection,
    incidentes: list[IncidenteExterno],
) -> int:
    """Importa Incidentes_Externos de forma idempotente (R15.3–R15.5).

    Usa *upsert* do SQLite (``INSERT ... ON CONFLICT(origem, id_externo) DO
    UPDATE``): reimportar o mesmo conjunto **não cria duplicatas** (R15.5).
    Todo registro é gravado com ``origem = "portal_dados_abertos"`` (R15.4).

    :param conn: Conexão SQLite aberta.
    :param incidentes: Incidentes_Externos normalizados a importar.
    :returns: Quantidade de incidentes processados (inseridos ou atualizados).
    """
    if not incidentes:
        return 0

    sql = """
        INSERT INTO incidente (
            municipio_id, tipo, centro_lat, centro_lng,
            origem, id_externo, gravidade_externa
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (origem, id_externo) DO UPDATE SET
            municipio_id      = excluded.municipio_id,
            tipo              = excluded.tipo,
            centro_lat        = excluded.centro_lat,
            centro_lng        = excluded.centro_lng,
            gravidade_externa = excluded.gravidade_externa
    """
    parametros = [
        (
            inc.municipio_id,
            inc.tipo,
            inc.centro_lat,
            inc.centro_lng,
            ORIGEM,
            inc.id_externo,
            inc.gravidade_externa,
        )
        for inc in incidentes
    ]
    conn.executemany(sql, parametros)
    conn.commit()
    return len(incidentes)


@dataclass(frozen=True)
class ResultadoSincronizacao:
    """Resultado de uma execução de :func:`sincronizar`.

    :param sucesso: ``True`` se busca e importação concluíram sem falha.
    :param importados: Quantidade de Incidentes_Externos importados.
    :param erro: Mensagem da falha quando ``sucesso`` é ``False`` (R15.6).
    """

    sucesso: bool
    importados: int = 0
    erro: Optional[str] = None


def sincronizar(
    conn: sqlite3.Connection,
    municipio: Any,
    cliente: Optional[httpx.Client] = None,
) -> ResultadoSincronizacao:
    """Orquestra a Sincronização_de_Dados_Abertos com degradação graciosa (R15.6).

    Executa :func:`buscar_incidentes` seguido de :func:`importar_incidentes`. Em
    caso de indisponibilidade, timeout, erro HTTP ou payload inválido, a falha é
    **capturada e registrada em log**; os dados existentes são **preservados** e
    o Aplicativo **continua operando** (a exceção não é propagada).

    :returns: :class:`ResultadoSincronizacao` indicando sucesso/falha e a
        contagem de importados.
    """
    try:
        incidentes = buscar_incidentes(municipio, cliente=cliente)
        importados = importar_incidentes(conn, incidentes)
    except (httpx.HTTPError, PayloadInvalido) as exc:
        logger.warning(
            "Sincronização com o Portal de Dados Abertos falhou; "
            "dados existentes preservados: %s",
            exc,
        )
        return ResultadoSincronizacao(sucesso=False, erro=str(exc))
    except Exception as exc:  # pragma: no cover - rede/parsing inesperado
        logger.exception(
            "Falha inesperada na Sincronização com o Portal de Dados Abertos; "
            "dados existentes preservados."
        )
        return ResultadoSincronizacao(sucesso=False, erro=str(exc))

    logger.info(
        "Sincronização com o Portal de Dados Abertos concluída: %d incidente(s).",
        importados,
    )
    return ResultadoSincronizacao(sucesso=True, importados=importados)


def _resolver_municipio_id(municipio: Any) -> int:
    """Extrai o ``id`` inteiro do município a partir de int, objeto ou linha."""
    if isinstance(municipio, int):
        return municipio
    # sqlite3.Row e dict suportam indexação por chave.
    try:
        return int(municipio["id"])  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        pass
    valor = getattr(municipio, "id", None)
    if valor is not None:
        return int(valor)
    raise TypeError(
        "municipio deve ser um int (id) ou possuir a chave/atributo 'id'"
    )
