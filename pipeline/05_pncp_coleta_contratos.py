# pipeline/05_pncp_coleta_contratos.py
# Etapa 5 — Coleta contratos federais do PNCP via API e salva em JSONL
#
# API oficial: https://pncp.gov.br/api/consulta/swagger-ui/index.html
# Endpoint: GET /v1/contratos
# - Filtra por data de publicação (últimos 6 meses por padrão)
# - Paginação automática (máximo 500 por página)
# - Salvamento incremental em JSONL (linha por linha)
# - Retry automático com backoff exponencial em caso de falha

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

# ── Configurações ──────────────────────────────────────────────────────────
BASE_URL  = "https://pncp.gov.br/api/consulta"
ENDPOINT  = f"{BASE_URL}/v1/contratos"

DAYS_BACK = 184                   # ~6 meses para trás a partir de hoje
PAGE_SIZES = [500, 200, 100, 50]  # tenta 500 primeiro; faz fallback se a API reclamar
SLEEP_BETWEEN_CALLS = 5.0         # pausa entre requisições (respeita a API)
TIMEOUT   = 180                   # segundos por requisição
MAX_RETRIES = 20                   # tentativas antes de desistir
BACKOFF_BASE = 1.8                # base do backoff exponencial

OUT_JSONL = Path("data/pncp_contratos_6m.jsonl")  # arquivo de saída

DIGITS_RE = re.compile(r"\D+")   # regex para extrair só dígitos

# ── Funções auxiliares ─────────────────────────────────────────────────────
def yyyymmdd(d: date) -> str:
    """Formata data no padrão que a API exige: AAAAMMDD."""
    return d.strftime("%Y%m%d")

def get_date_range() -> tuple[str, str]:
    """Calcula o intervalo dinâmico: hoje menos DAYS_BACK até hoje."""
    today = date.today()
    start = today - timedelta(days=DAYS_BACK)
    return yyyymmdd(start), yyyymmdd(today)

def only_digits(s: Optional[str]) -> str:
    """Remove tudo que não for dígito de uma string."""
    return DIGITS_RE.sub("", s or "")

def extract_cnpj(item: Dict[str, Any]) -> Optional[str]:
    """
    Extrai o CNPJ do fornecedor somente se for Pessoa Jurídica (PJ)
    com CNPJ válido de 14 dígitos.
    MEI é sempre PJ — CPFs e CNPJs inválidos são descartados.
    """
    tipo = (item.get("tipoPessoa") or "").upper()
    ni   = only_digits(str(item.get("niFornecedor") or ""))
    if tipo == "PJ" and len(ni) == 14:
        return ni
    return None

def safe_request(params: Dict[str, Any]) -> requests.Response:
    """
    Faz a requisição GET com retry e backoff exponencial.
    Em caso de falha temporária (timeout, erro de rede), aguarda e tenta novamente.
    """
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                ENDPOINT,
                params=params,
                headers={"accept": "*/*"},
                timeout=TIMEOUT
            )
            return r
        except Exception as e:
            last_err = e
            wait = BACKOFF_BASE ** (attempt - 1)
            print(f"  [AVISO] Tentativa {attempt}/{MAX_RETRIES} falhou: {e}. Aguardando {wait:.1f}s...")
            time.sleep(wait)
    raise RuntimeError(f"❌ Falha após {MAX_RETRIES} tentativas. Último erro: {last_err}")

def fetch_page(data_inicial: str, data_final: str, pagina: int, tamanho: int) -> Dict[str, Any]:
    """
    Busca uma página de contratos na API do PNCP.
    Retorna o JSON da resposta ou um dict especial para indicar fim dos dados.
    """
    params = {
        "dataInicial":   data_inicial,
        "dataFinal":     data_final,
        "pagina":        pagina,
        "tamanhoPagina": tamanho,
    }
    r = safe_request(params)

    if r.status_code == 204:          # sem conteúdo = fim da paginação
        return {"_sem_conteudo": True}

    if r.status_code == 400:          # erro de parâmetro (ex: tamanhoPagina inválido)
        try:
            err = r.json()
        except Exception:
            err = {"mensagem": r.text}
        raise ValueError(err)

    r.raise_for_status()
    return r.json()

# ── Função principal ───────────────────────────────────────────────────────
def main():
    data_inicial, data_final = get_date_range()
    print(f"📅 Coletando contratos de {data_inicial} até {data_final}")

    # Garante que a pasta de saída existe
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    # Remove arquivo anterior para começar do zero
    if OUT_JSONL.exists():
        OUT_JSONL.unlink()
        print(f"🗑️  Arquivo anterior removido: {OUT_JSONL}")

    total      = 0
    pagina     = 1
    size_idx   = 0   # índice em PAGE_SIZES (começa tentando 500)

    print(f"💾 Salvando em: {OUT_JSONL}\n")

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        while True:
            tamanho = PAGE_SIZES[size_idx]

            try:
                payload = fetch_page(data_inicial, data_final, pagina, tamanho)

            except ValueError as ve:
                # A API reclamou do tamanhoPagina — tenta o próximo menor
                msg = str(ve).lower()
                if "tamanho" in msg and size_idx < len(PAGE_SIZES) - 1:
                    size_idx += 1
                    print(f"  [AVISO] Ajustando tamanhoPagina para {PAGE_SIZES[size_idx]}...")
                    continue
                raise

            # Fim da paginação
            if payload.get("_sem_conteudo"):
                print("✅ API retornou 204 — todos os dados foram coletados.")
                break

            registros: List[Dict[str, Any]] = payload.get("data") or []

            if not registros:
                print("✅ Página vazia — coleta encerrada.")
                break

            # Enriquece cada registro com o CNPJ extraído e salva linha a linha
            for item in registros:
                item["_fornecedor_cnpj"] = extract_cnpj(item)
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

            total += len(registros)

            print(
                f"  Página {pagina:>4} | "
                f"lote={len(registros):>3} | "
                f"total={total:>7,} | "
                f"páginas restantes={payload.get('paginasRestantes', '?')}"
            )

            pagina += 1
            time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"\n🏁 Coleta finalizada: {total:,} contratos salvos em {OUT_JSONL}")

if __name__ == "__main__":
    main()