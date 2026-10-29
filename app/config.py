"""Configuração do Aplicativo Refúgio.

As variáveis são lidas de variáveis de ambiente com os padrões definidos no
design. A fonte principal (Portal Brasileiro de Dados Abertos — dados.gov.br)
é habilitada por padrão (R15.7); as fontes opcionais (Defesa Civil SP e Defesa
Civil Alerta) permanecem desligadas por padrão.
"""

from __future__ import annotations

import os


def _ler_bool(nome: str, padrao: bool) -> bool:
    """Lê uma variável de ambiente booleana.

    Valores considerados verdadeiros: ``1``, ``true``, ``yes``, ``on`` (sem
    diferenciar maiúsculas/minúsculas). Qualquer outro valor é falso.
    """
    bruto = os.environ.get(nome)
    if bruto is None:
        return padrao
    return bruto.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _ler_int(nome: str, padrao: int) -> int:
    """Lê uma variável de ambiente inteira, caindo no padrão se inválida."""
    bruto = os.environ.get(nome)
    if bruto is None or bruto.strip() == "":
        return padrao
    try:
        return int(bruto.strip())
    except ValueError:
        return padrao


def _ler_str(nome: str, padrao: str) -> str:
    """Lê uma variável de ambiente textual, caindo no padrão se ausente."""
    bruto = os.environ.get(nome)
    if bruto is None or bruto.strip() == "":
        return padrao
    return bruto.strip()


# Intervalo de polling padrão: 6 horas (21600 segundos).
POLLING_PADRAO_SEGUNDOS = 21600

# --- Portal Brasileiro de Dados Abertos (dados.gov.br) — R15 (habilitado) ---
FONTE_DADOSGOVBR_HABILITADA: bool = _ler_bool("FONTE_DADOSGOVBR_HABILITADA", True)
FONTE_DADOSGOVBR_POLLING_SEGUNDOS: int = _ler_int(
    "FONTE_DADOSGOVBR_POLLING_SEGUNDOS", POLLING_PADRAO_SEGUNDOS
)
FONTE_DADOSGOVBR_URL: str = _ler_str(
    "FONTE_DADOSGOVBR_URL",
    "https://dados.gov.br/api/incidentes",
)

# --- Defesa Civil SP (opcional, desligada por padrão) ---
FONTE_DEFESACIVILSP_HABILITADA: bool = _ler_bool(
    "FONTE_DEFESACIVILSP_HABILITADA", False
)
FONTE_DEFESACIVILSP_POLLING_SEGUNDOS: int = _ler_int(
    "FONTE_DEFESACIVILSP_POLLING_SEGUNDOS", POLLING_PADRAO_SEGUNDOS
)

# --- Defesa Civil Alerta (opcional, desligada por padrão) ---
FONTE_DEFESACIVILALERTA_HABILITADA: bool = _ler_bool(
    "FONTE_DEFESACIVILALERTA_HABILITADA", False
)
FONTE_DEFESACIVILALERTA_POLLING_SEGUNDOS: int = _ler_int(
    "FONTE_DEFESACIVILALERTA_POLLING_SEGUNDOS", POLLING_PADRAO_SEGUNDOS
)

# --- Caminhos de dados (SQLite em arquivo e fotos em disco) ---
CAMINHO_BANCO: str = _ler_str("REFUGIO_CAMINHO_BANCO", "/data/refugio.db")
CAMINHO_FOTOS: str = _ler_str("REFUGIO_CAMINHO_FOTOS", "/data/fotos")
