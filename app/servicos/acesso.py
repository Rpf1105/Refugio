"""Controle de Acesso por perfil do protótipo Refúgio.

Módulo puro e sem dependências de banco que distingue os perfis de usuário
``cidadao`` e ``orgao_responsavel`` e protege as operações de gestão (cadastro
de Área_Afetada/Abrigo, validação de Relato, sincronização manual de Dados
Abertos) exigindo o perfil de Órgão_Responsável (R6.4).

No protótipo não há autenticação robusta: o perfil é determinado por um
cabeçalho HTTP simples, ``X-Perfil``, conforme o design ("o perfil pode ser
determinado por um cabeçalho/sessão simples; não há autenticação robusta").
A camada de API lê o valor do cabeçalho, resolve o perfil com
``resolver_perfil`` e protege os endpoints de gestão com
``exigir_orgao_responsavel``.

Diferentemente das validações de entrada (``ErroValidacao`` → HTTP 400), a
negação de acesso corresponde a HTTP 403. Por isso este módulo define a exceção
dedicada ``ErroAcesso``, que a camada de API converte na resposta JSON
padronizada ``{ "erro": <mensagem> }`` com status 403.

Referências de design:
- Serviços de Aplicação — "Controle de Acesso" (R6.4)
- Error Handling — "Acesso negado (403)" → "acesso não autorizado"
- Considerações do Protótipo — "Autenticação simplificada" (sessão/cabeçalho)
"""

# Perfis de usuário reconhecidos (armazenados em ``usuario.perfil``).
PERFIL_CIDADAO = "cidadao"
PERFIL_ORGAO = "orgao_responsavel"

# Conjunto dos perfis válidos, usado na resolução a partir do cabeçalho.
PERFIS_VALIDOS = (PERFIL_CIDADAO, PERFIL_ORGAO)

# Nome do cabeçalho HTTP que transporta o perfil no protótipo.
CABECALHO_PERFIL = "X-Perfil"

# Mensagem exigida pelo critério de aceitação de acesso negado (R6.4).
MSG_ACESSO_NAO_AUTORIZADO = "acesso não autorizado"


class ErroAcesso(Exception):
    """Erro de controle de acesso (HTTP 403).

    Sinaliza que a operação de gestão foi negada por falta do perfil de
    Órgão_Responsável. Carrega a ``mensagem`` destinada ao usuário (por padrão
    "acesso não autorizado"), de modo a alimentar a resposta JSON padronizada
    ``{ "erro": <mensagem> }`` usada pela API com status 403.
    """

    def __init__(self, mensagem: str = MSG_ACESSO_NAO_AUTORIZADO):
        super().__init__(mensagem)
        self.mensagem = mensagem


def resolver_perfil(valor_cabecalho) -> str:
    """Resolve o perfil do usuário a partir do valor do cabeçalho ``X-Perfil``.

    O valor é normalizado (aparado e em minúsculas) e comparado aos perfis
    válidos. Quando ausente, vazio ou desconhecido, assume-se o perfil menos
    privilegiado, ``cidadao``, de forma que o acesso às operações de gestão
    jamais seja concedido por omissão (padrão seguro).

    Args:
        valor_cabecalho: Conteúdo bruto do cabeçalho ``X-Perfil`` (ou ``None``
            quando o cabeçalho não foi enviado).

    Returns:
        O perfil resolvido: ``PERFIL_CIDADAO`` ou ``PERFIL_ORGAO``.
    """
    if valor_cabecalho is None:
        return PERFIL_CIDADAO

    perfil = valor_cabecalho.strip().lower()
    if perfil in PERFIS_VALIDOS:
        return perfil

    return PERFIL_CIDADAO


def eh_orgao_responsavel(perfil) -> bool:
    """Indica se o ``perfil`` informado é o de Órgão_Responsável.

    Args:
        perfil: Perfil do usuário (tipicamente obtido de ``resolver_perfil``).

    Returns:
        ``True`` quando ``perfil`` é exatamente ``PERFIL_ORGAO``; ``False`` caso
        contrário.
    """
    return perfil == PERFIL_ORGAO


def exigir_orgao_responsavel(perfil) -> None:
    """Protege uma operação de gestão exigindo o perfil de Órgão_Responsável.

    Guarda usada pelos endpoints de gestão — cadastro de Área_Afetada/Abrigo,
    validação de Relato e sincronização manual de Dados Abertos — para garantir
    que apenas o Órgão_Responsável as execute (R6.4).

    Args:
        perfil: Perfil do usuário (tipicamente obtido de ``resolver_perfil``).

    Returns:
        ``None`` quando o perfil é o de Órgão_Responsável e a operação é
        permitida.

    Raises:
        ErroAcesso: quando ``perfil`` não é o de Órgão_Responsável; a instância
            carrega a mensagem "acesso não autorizado" (HTTP 403).
    """
    if not eh_orgao_responsavel(perfil):
        raise ErroAcesso(MSG_ACESSO_NAO_AUTORIZADO)
