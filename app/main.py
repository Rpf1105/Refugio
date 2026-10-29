"""Ponto de entrada da aplicação FastAPI do Refúgio.

Este módulo estabelece o esqueleto do backend (R8.1 — FastAPI em Python):

- cria a instância da aplicação com o nome exibido "Refúgio";
- inicializa o banco de dados no *startup* (schema + seed idempotentes), de modo
  que o Município padrão "Ribeirão Preto" e os usuários de exemplo existam antes
  de atender requisições;
- monta os arquivos estáticos em ``/static`` (assets do frontend) e as fotos de
  Relatos em ``/fotos`` (diretório ``config.CAMINHO_FOTOS``), criando o diretório
  de fotos quando ausente para não falhar na montagem;
- disponibiliza a dependência :func:`get_conn`, que abre uma conexão SQLite por
  requisição e a fecha ao final, para ser reutilizada pelos endpoints;
- registra os *exception handlers* que convertem as exceções de domínio na
  resposta JSON padronizada ``{ "erro": <mensagem>, "campo": <opcional> }`` com
  os status apropriados (400 validação, 403 acesso negado, 404 não encontrado);
- define os modelos Pydantic compartilhados de requisição/resposta reutilizados
  pelos endpoints das tarefas posteriores (9.2, 9.3, 9.4, 14.1).

Os routers da API e as rotas de página são adicionados pelas tarefas seguintes;
a estrutura abaixo foi pensada para que eles possam ser incluídos de forma limpa
(ver :func:`_registrar_routers`). Por ora, uma rota raiz de verificação
("health/root") garante que a aplicação suba e responda.

Referências de design:
- Components and Interfaces — "Backend (FastAPI) — Rotas HTTP" (R10.1, R10.2)
- Error Handling — respostas de erro padronizadas ``{ "erro", "campo" }``
- Data Models — campos das entidades Área_Afetada, Abrigo e Pedido_de_Ajuda
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Iterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.dados.db import conectar, inicializar_banco
from app.dominio.rotas import RotaSeguraNaoEncontradaError
from app.dominio.validacao import ErroValidacao
from app.servicos.acesso import ErroAcesso

logger = logging.getLogger(__name__)

# Nome exibido do Aplicativo (R14.5). Usado como título do app e na documentação.
NOME_APP = "Refúgio"

# Diretório dos arquivos estáticos do frontend (CSS/JS/imagens de UI).
_DIRETORIO_STATIC = os.path.join(os.path.dirname(__file__), "web", "static")

# Diretório dos templates HTML servidos nas rotas de página (R10.1, R10.2).
_DIRETORIO_TEMPLATES = os.path.join(os.path.dirname(__file__), "web", "templates")

# Mapeamento rota → arquivo de template para as 4 telas do Aplicativo
# (Início, Mapa, Ocorrência, Pedir ajuda). As páginas são HTML estático
# (sem placeholders Jinja), portanto são lidas e devolvidas como HTMLResponse.
_PAGINAS: dict[str, str] = {
    "/": "inicio.html",
    "/mapa": "mapa.html",
    "/ocorrencia": "ocorrencia.html",
    "/pedir-ajuda": "pedir-ajuda.html",
}


# ---------------------------------------------------------------------------
# Modelos Pydantic compartilhados
# ---------------------------------------------------------------------------
#
# Mantidos neste módulo (``app.main``) por simplicidade do protótipo. Os routers
# das tarefas 9.2–9.4 importam estes modelos a partir daqui. Caso o conjunto de
# modelos cresça, eles podem ser movidos para ``app/web/modelos.py`` sem alterar
# o contrato (basta reexportá-los aqui).


class ErroResposta(BaseModel):
    """Corpo JSON padronizado das respostas de erro da API.

    Reproduz o formato ``{ "erro": <mensagem>, "campo": <opcional> }`` exigido
    pelo design. O campo ``campo`` é omitido da resposta quando ``None`` (os
    handlers serializam com ``exclude_none``), ficando presente apenas nas
    falhas de validação que apontam um campo específico (R4.2–R4.4, R11.2).
    """

    erro: str = Field(..., description="Mensagem de erro destinada ao Cidadão.")
    campo: Optional[str] = Field(
        default=None,
        description="Nome do campo que originou a falha (apenas em validações).",
    )


class AreaCriar(BaseModel):
    """Dados para cadastrar uma Área_Afetada (POST /api/areas, R6.1).

    O polígono é a lista de vértices ``[[lat, lng], ...]`` que delimita a região
    afetada; o ``nivel_gravidade`` segue o enum de armazenamento
    ('baixo', 'medio', 'alto').
    """

    descricao: str = Field(..., description="Descrição da Área_Afetada.")
    nivel_gravidade: str = Field(
        ..., description="Nível de gravidade: 'baixo', 'medio' ou 'alto'."
    )
    poligono: list[list[float]] = Field(
        ..., description="Vértices do polígono como pares [lat, lng]."
    )
    municipio_id: int = Field(..., description="Município ao qual a Área pertence.")


class AbrigoCriar(BaseModel):
    """Dados para cadastrar um Abrigo (POST /api/abrigos, R6.2).

    Registra nome, endereço, localização geográfica (``lat``/``lng``) e
    capacidade (opcional) do Abrigo.
    """

    nome: str = Field(..., description="Nome do Abrigo.")
    endereco: str = Field(..., description="Endereço do Abrigo.")
    lat: float = Field(..., description="Latitude do Abrigo em graus.")
    lng: float = Field(..., description="Longitude do Abrigo em graus.")
    capacidade: Optional[int] = Field(
        default=None, description="Capacidade de pessoas do Abrigo (opcional)."
    )
    municipio_id: int = Field(..., description="Município ao qual o Abrigo pertence.")


class PedidoCriar(BaseModel):
    """Dados para publicar um Pedido_de_Ajuda (POST /api/pedidos, R11.1).

    A ``descricao`` é obrigatória (R11.2) e passa pelo Filtro_de_Conteúdo
    (R11.3–R11.5) na camada de serviço; a localização é opcional.
    """

    descricao: str = Field(..., description="Descrição da situação do Cidadão.")
    lat: Optional[float] = Field(default=None, description="Latitude do Pedido.")
    lng: Optional[float] = Field(default=None, description="Longitude do Pedido.")
    municipio_id: int = Field(..., description="Município ao qual o Pedido pertence.")
    usuario_id: int = Field(..., description="Usuário que publica o Pedido.")


# ---------------------------------------------------------------------------
# Dependência de conexão com o banco
# ---------------------------------------------------------------------------


def get_conn() -> Iterator[sqlite3.Connection]:
    """Dependência FastAPI que fornece uma conexão SQLite por requisição.

    Abre a conexão (via :func:`app.dados.db.conectar`) no início do tratamento
    da requisição e garante o seu fechamento ao final, mesmo em caso de erro.
    Os endpoints das tarefas posteriores declaram ``conn = Depends(get_conn)``
    para obter a conexão e repassá-la aos serviços de domínio.

    Yields:
        A conexão SQLite aberta para a requisição corrente.
    """
    conexao = conectar()
    try:
        yield conexao
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Exception handlers (respostas de erro padronizadas)
# ---------------------------------------------------------------------------


async def _tratar_erro_validacao(
    request: Request, exc: ErroValidacao
) -> JSONResponse:
    """Converte :class:`ErroValidacao` em resposta JSON 400.

    Produz ``{ "erro": <mensagem>, "campo": <campo> }``; o ``campo`` é omitido
    quando ausente (``None``). Cobre as validações de Relato e Pedido de Ajuda
    (R4.2–R4.4, R11.2).
    """
    corpo = ErroResposta(erro=exc.mensagem, campo=exc.campo)
    return JSONResponse(status_code=400, content=corpo.model_dump(exclude_none=True))


async def _tratar_erro_acesso(request: Request, exc: ErroAcesso) -> JSONResponse:
    """Converte :class:`ErroAcesso` em resposta JSON 403 ("acesso não autorizado").

    Cobre a negação de operações de gestão a usuários sem o perfil de
    Órgão_Responsável (R6.4).
    """
    corpo = ErroResposta(erro=exc.mensagem)
    return JSONResponse(status_code=403, content=corpo.model_dump(exclude_none=True))


async def _tratar_rota_nao_encontrada(
    request: Request, exc: RotaSeguraNaoEncontradaError
) -> JSONResponse:
    """Converte :class:`RotaSeguraNaoEncontradaError` em resposta JSON 404.

    Sinaliza a ausência de Rota_Segura livre entre origem e destino (R3.3),
    usada pelo endpoint ``GET /api/rotas`` (tarefa 9.4).
    """
    corpo = ErroResposta(erro=str(exc))
    return JSONResponse(status_code=404, content=corpo.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Montagem de estáticos e registro de routers
# ---------------------------------------------------------------------------


def _montar_estaticos(app: FastAPI) -> None:
    """Monta os arquivos estáticos em ``/static`` e as fotos em ``/fotos``.

    O diretório de fotos (``config.CAMINHO_FOTOS``) é criado quando ausente para
    que a montagem não falhe no primeiro *startup*; o diretório de estáticos do
    frontend acompanha o código-fonte.
    """
    os.makedirs(_DIRETORIO_STATIC, exist_ok=True)
    os.makedirs(config.CAMINHO_FOTOS, exist_ok=True)

    app.mount("/static", StaticFiles(directory=_DIRETORIO_STATIC), name="static")
    app.mount("/fotos", StaticFiles(directory=config.CAMINHO_FOTOS), name="fotos")


def _registrar_handlers(app: FastAPI) -> None:
    """Registra os *exception handlers* das exceções de domínio."""
    app.add_exception_handler(ErroValidacao, _tratar_erro_validacao)
    app.add_exception_handler(ErroAcesso, _tratar_erro_acesso)
    app.add_exception_handler(
        RotaSeguraNaoEncontradaError, _tratar_rota_nao_encontrada
    )


def _ler_template(nome_arquivo: str) -> str:
    """Lê o conteúdo de um template HTML do diretório de templates.

    Os templates são HTML estático (sem placeholders Jinja), de modo que basta
    ler e devolver o conteúdo do arquivo como texto UTF-8.
    """
    caminho = os.path.join(_DIRETORIO_TEMPLATES, nome_arquivo)
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return arquivo.read()


def _criar_rota_pagina(nome_arquivo: str):
    """Cria o *handler* de uma rota de página que serve ``nome_arquivo``.

    Fecha sobre ``nome_arquivo`` para que cada rota devolva o seu template
    correspondente como :class:`~fastapi.responses.HTMLResponse`.
    """

    async def _pagina() -> HTMLResponse:
        return HTMLResponse(content=_ler_template(nome_arquivo))

    return _pagina


def _registrar_paginas(app: FastAPI) -> None:
    """Registra as rotas de página das 4 telas do Aplicativo (R10.1, R10.2).

    Serve ``/`` → Início, ``/mapa`` → Mapa, ``/ocorrencia`` → Ocorrência e
    ``/pedir-ajuda`` → Pedir ajuda, devolvendo o HTML estático de cada template
    sob ``app/web/templates``.
    """
    for caminho, nome_arquivo in _PAGINAS.items():
        app.add_api_route(
            caminho,
            _criar_rota_pagina(nome_arquivo),
            methods=["GET"],
            response_class=HTMLResponse,
            include_in_schema=False,
            tags=["paginas"],
        )


def _registrar_routers(app: FastAPI) -> None:
    """Registra os routers da API e as rotas de página (tarefa 14.1).

    Os módulos de router (``app/web/rotas_*.py``) importam :func:`get_conn` — e
    alguns, os modelos Pydantic — a partir de ``app.main``. Para evitar o ciclo
    de importação, os routers são importados **aqui dentro** (importação
    adiada), de modo que ``app.main`` já esteja totalmente definido quando os
    routers importarem dele.
    """
    from app.web.rotas_municipios_areas_abrigos import router as router_municipios
    from app.web.rotas_relatos_incidentes import router as router_relatos
    from app.web.rotas_rotas_pedidos import router as router_rotas_pedidos
    from app.web.rotas_incidentes_externos import router as router_externos

    app.include_router(router_municipios)
    app.include_router(router_relatos)
    app.include_router(router_rotas_pedidos)
    app.include_router(router_externos)

    _registrar_paginas(app)


# ---------------------------------------------------------------------------
# Job periódico da Sincronização de Dados Abertos (R15)
# ---------------------------------------------------------------------------


def _job_sincronizacao() -> None:
    """Executa uma Sincronização_de_Dados_Abertos para o Município padrão (R15.1).

    Callable sem argumentos passado ao Agendador: abre uma conexão, resolve o
    ``id`` do Município padrão (``padrao = 1``), chama
    :func:`app.integracao.dados_abertos.sincronizar` e fecha a conexão. Nunca
    propaga exceções para fora do agendador — :func:`sincronizar` já degrada
    graciosamente (R15.6), e qualquer falha inesperada (ex.: ausência do
    Município padrão) é registrada em log sem derrubar o job.
    """
    from app.integracao.dados_abertos import sincronizar

    conexao = conectar()
    try:
        linha = conexao.execute(
            "SELECT id FROM municipio WHERE padrao = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if linha is None:
            logger.warning(
                "Sincronização agendada ignorada: Município padrão não encontrado."
            )
            return
        sincronizar(conexao, int(linha["id"]))
    except Exception:  # pragma: no cover - salvaguarda do agendador
        logger.exception(
            "Falha inesperada no job de Sincronização de Dados Abertos; "
            "o agendador segue ativo."
        )
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Construção da aplicação
# ---------------------------------------------------------------------------


def criar_app() -> FastAPI:
    """Cria e configura a instância FastAPI do Refúgio.

    Encapsula a configuração do app (título, handlers, estáticos, routers e o
    gancho de *startup* que inicializa o banco) numa fábrica, o que facilita o
    teste isolado e a reutilização.

    Returns:
        A instância :class:`fastapi.FastAPI` pronta para servir.
    """
    app = FastAPI(title=NOME_APP)

    @app.on_event("startup")
    def _ao_iniciar() -> None:
        """Inicializa o banco e inicia o agendador no startup (R7.1, R15.1).

        Primeiro aplica schema + seed idempotentes (R7.1); em seguida inicia o
        Agendador periódico da Sincronização_de_Dados_Abertos, que só agenda
        requisições quando ``FONTE_DADOSGOVBR_HABILITADA`` está ligado (R15.1);
        quando desligado, o agendador não é iniciado e as requisições são
        omitidas (R15.7). O agendador resultante (ou ``None``) é guardado em
        ``app.state.agendador`` para ser desligado no shutdown.
        """
        conexao = inicializar_banco()
        conexao.close()

        # Importação adiada para evitar acoplar o módulo à integração no topo
        # (e manter o paralelo com o registro adiado dos routers).
        from app.integracao.agendador import iniciar_agendador

        app.state.agendador = iniciar_agendador(_job_sincronizacao)

    @app.on_event("shutdown")
    def _ao_desligar() -> None:
        """Desliga o Agendador da Sincronização_de_Dados_Abertos, se ativo."""
        agendador = getattr(app.state, "agendador", None)
        if agendador is not None:
            agendador.shutdown(wait=False)
            app.state.agendador = None

    @app.get("/health", tags=["infra"])
    def health() -> dict[str, str]:
        """Verificação simples de saúde da aplicação.

        Retorna o nome do Aplicativo e um status "ok"; útil para testes de
        fumaça e sondagem de disponibilidade.
        """
        return {"status": "ok", "app": NOME_APP}

    _registrar_handlers(app)
    _montar_estaticos(app)
    _registrar_routers(app)

    return app


# Instância padrão servida pelo Uvicorn (``uvicorn app.main:app``).
app = criar_app()
