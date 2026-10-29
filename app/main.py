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

import os
import sqlite3
from typing import Iterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.dados.db import conectar, inicializar_banco
from app.dominio.rotas import RotaSeguraNaoEncontradaError
from app.dominio.validacao import ErroValidacao
from app.servicos.acesso import ErroAcesso

# Nome exibido do Aplicativo (R14.5). Usado como título do app e na documentação.
NOME_APP = "Refúgio"

# Diretório dos arquivos estáticos do frontend (CSS/JS/imagens de UI).
_DIRETORIO_STATIC = os.path.join(os.path.dirname(__file__), "web", "static")


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


def _registrar_routers(app: FastAPI) -> None:
    """Registra os routers da API e as rotas de página.

    Ponto de extensão para as tarefas 9.2–9.4 (endpoints da API) e 14.1 (rotas
    de página e fiação final). Mantido vazio por ora; os routers serão incluídos
    aqui com ``app.include_router(...)`` sem alterar o restante do módulo.
    """
    # As tarefas seguintes adicionam, por exemplo:
    #   from app.web.rotas_api import router as router_api
    #   app.include_router(router_api)
    return None


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
        """Inicializa o banco no startup (schema + seed idempotentes, R7.1)."""
        conexao = inicializar_banco()
        conexao.close()

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
