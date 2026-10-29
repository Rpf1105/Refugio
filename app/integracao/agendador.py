"""Agendador periódico da Sincronização_de_Dados_Abertos (R15).

Para o protótipo monolítico (um único processo FastAPI), o disparo periódico
da sincronização com o Portal_de_Dados_Abertos usa um agendador simples em
processo baseado em ``APScheduler`` (``BackgroundScheduler``), configurado com
um *interval trigger* de 6 horas (21600 s) e iniciado no *startup* da aplicação
(R15.1).

Decisões de projeto relevantes:

- **Habilitação por configuração (R15.7):** o agendador só é iniciado quando a
  Sincronização_de_Dados_Abertos está habilitada (por padrão,
  ``config.FONTE_DADOSGOVBR_HABILITADA``). Quando desabilitada, o agendador
  **não** é iniciado e **nenhuma** requisição ao Portal é agendada — as
  requisições são integralmente omitidas.
- **Injeção de dependência da tarefa (``job``):** o agendador não importa a
  função de sincronização diretamente. Ela é recebida como parâmetro
  (``job``), mantendo este módulo desacoplado de
  ``app.integracao.dados_abertos`` e facilmente testável.
- **Relógio (clock) injetável:** para testabilidade, o agendador recebe o
  relógio por injeção. O ``BackgroundScheduler`` do APScheduler aceita um
  ``timezone`` (via parâmetro ``clock``); além disso, o intervalo configurado
  é exposto por :func:`intervalo_configurado`, permitindo que um teste com um
  *clock* falso verifique a cadência de 6 h sem dormir de verdade.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app import config

logger = logging.getLogger(__name__)

# Identificador do job da sincronização periódica no agendador.
ID_JOB_SINCRONIZACAO = "sincronizacao_dados_abertos"


def intervalo_configurado(intervalo_segundos: Optional[int] = None) -> int:
    """Retorna o intervalo de *polling* em segundos.

    Usa ``intervalo_segundos`` quando informado; caso contrário, recorre a
    ``config.FONTE_DADOSGOVBR_POLLING_SEGUNDOS`` (padrão: 21600 s = 6 h). É
    exposto para que testes com um *clock* falso possam afirmar a cadência de
    6 h (R15.1) sem precisar iniciar o agendador real.
    """
    if intervalo_segundos is None:
        return config.FONTE_DADOSGOVBR_POLLING_SEGUNDOS
    return intervalo_segundos


def criar_agendador(clock=None) -> BackgroundScheduler:
    """Cria um ``BackgroundScheduler`` do APScheduler.

    O relógio é injetável para testabilidade: o ``BackgroundScheduler`` aceita
    um ``timezone`` que controla a base de tempo usada para calcular os
    disparos do *interval trigger*. Passe esse ``timezone`` (ou um objeto de
    relógio compatível) em ``clock`` para verificar o intervalo de 6 h com uma
    base de tempo controlada nos testes; quando ``clock`` é ``None``, usa-se o
    fuso padrão do sistema.

    O agendador é apenas **criado** (não iniciado) por esta função, de modo que
    testes possam inspecioná-lo sem efeitos colaterais.
    """
    if clock is not None:
        return BackgroundScheduler(timezone=clock)
    return BackgroundScheduler()


def iniciar_agendador(
    job: Callable[[], None],
    clock=None,
    habilitada: Optional[bool] = None,
    intervalo_segundos: Optional[int] = None,
) -> Optional[BackgroundScheduler]:
    """Agenda e inicia a Sincronização_de_Dados_Abertos a cada 6 h (R15.1).

    Parâmetros:
        job: função (sem argumentos) a ser executada a cada intervalo. É
            recebida por injeção de dependência — tipicamente um ``callable``
            que encapsula ``app.integracao.dados_abertos.sincronizar(...)`` —
            mantendo este módulo desacoplado e testável.
        clock: relógio/``timezone`` injetável repassado a
            :func:`criar_agendador` (ver documentação dessa função).
        habilitada: quando ``None`` (padrão), usa
            ``config.FONTE_DADOSGOVBR_HABILITADA``.
        intervalo_segundos: quando ``None`` (padrão), usa
            ``config.FONTE_DADOSGOVBR_POLLING_SEGUNDOS`` (21600 s = 6 h).

    Comportamento:
        - **Habilitada (R15.1):** agenda ``job`` em um *interval trigger* de
          ``intervalo_segundos`` segundos, inicia o agendador e o retorna.
        - **Desabilitada (R15.7):** **não** agenda nem inicia nada — as
          requisições ao Portal são integralmente omitidas — e retorna
          ``None``.

    Retorna:
        O ``BackgroundScheduler`` em execução quando habilitada; ``None``
        quando desabilitada.
    """
    if habilitada is None:
        habilitada = config.FONTE_DADOSGOVBR_HABILITADA

    if not habilitada:
        # R15.7: sincronização desabilitada por configuração — omitir as
        # requisições ao Portal; nada é agendado ou iniciado.
        logger.info(
            "Sincronização de Dados Abertos desabilitada por configuração "
            "(R15.7); agendador não iniciado e requisições omitidas."
        )
        return None

    intervalo = intervalo_configurado(intervalo_segundos)

    agendador = criar_agendador(clock=clock)
    agendador.add_job(
        job,
        trigger="interval",
        seconds=intervalo,
        id=ID_JOB_SINCRONIZACAO,
        replace_existing=True,
    )
    agendador.start()
    logger.info(
        "Agendador da Sincronização de Dados Abertos iniciado "
        "(intervalo=%ss, ~%.1fh).",
        intervalo,
        intervalo / 3600,
    )
    return agendador
