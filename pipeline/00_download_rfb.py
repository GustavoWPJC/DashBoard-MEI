# pipeline/00_download_rfb.py
# Etapa 0 — Baixa os arquivos da Receita Federal automaticamente
#
# Espelho: https://dados-abertos-rf-cnpj.casadosdados.com.br
# Organizado por data: /arquivos/AAAA-MM-DD/NomeArquivo/NomeArquivo.zip
#
# ⚠️  Os arquivos são grandes (~5GB no total comprimido).
#     Tenha pelo menos 20GB livres em disco para os CSVs descompactados.
#
# Uso:
#   python pipeline/00_download_rfb.py

import requests
import zipfile
import sys
from pathlib import Path
from datetime import datetime

# ── Configurações ──────────────────────────────────────────────────────────
BASE_URL  = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos"
DATA_LOTE = "2026-05-10"   # ← pasta mais recente do espelho
OUT_DIR   = Path("data/rf_cnpj_csv")

# Arquivos que precisamos (nome da pasta = nome do arquivo)
ARQUIVOS = (
    [f"Empresas{i}" for i in range(10)] +
    [f"Estabelecimentos{i}" for i in range(10)] +
    ["Simples", "Cnaes"]
)

TIMEOUT    = 300
CHUNK_SIZE = 1024 * 1024 * 8  # 8MB

# ── Helpers ────────────────────────────────────────────────────────────────
def tamanho_legivel(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def baixar_arquivo(nome: str) -> bool:
    """
    Baixa um arquivo em chunks mostrando progresso.
    Retorna True se baixou com sucesso, False se falhou.
    """
    url     = f"{BASE_URL}/{DATA_LOTE}/{nome}.zip"
    destino = OUT_DIR / f"{nome}.zip"

    # Pula se já foi baixado
    if destino.exists() and destino.stat().st_size > 1000:
        print(f"   ⏭️  Já existe: {nome}.zip ({tamanho_legivel(destino.stat().st_size)})")
        return True

    print(f"   ⬇️  Baixando: {nome}.zip")
    print(f"      URL: {url}")

    try:
        r = requests.get(url, stream=True, timeout=TIMEOUT)

        if r.status_code == 404:
            print(f"   ⚠️  Não encontrado (404): {nome} — pulando")
            return False

        r.raise_for_status()

        total   = int(r.headers.get("content-length", 0))
        baixado = 0
        inicio  = datetime.now()

        with destino.open("wb") as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    baixado += len(chunk)
                    if total:
                        pct = baixado / total * 100
                        print(f"\r      {pct:.1f}% — {tamanho_legivel(baixado)} / {tamanho_legivel(total)}", end="", flush=True)

        duracao = (datetime.now() - inicio).seconds
        print(f"\r      ✅ {tamanho_legivel(baixado)} em {duracao}s{' ' * 20}")
        return True

    except Exception as e:
        print(f"\n   ❌ Erro ao baixar {nome}: {e}")
        if destino.exists():
            destino.unlink()  # remove arquivo corrompido
        return False

def descompactar(nome: str) -> bool:
    """
    Descompacta o ZIP na pasta OUT_DIR e remove o ZIP após extrair.
    """
    zip_path = OUT_DIR / f"{nome}.zip"
    try:
        print(f"   📦 Descompactando: {nome}.zip")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(OUT_DIR)
        zip_path.unlink()  # apaga o ZIP para economizar disco
        print(f"      ✅ Extraído e ZIP removido")
        return True
    except Exception as e:
        print(f"      ❌ Erro ao descompactar {nome}.zip: {e}")
        return False

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("📥 DOWNLOAD — ESPELHO DADOS ABERTOS RFB")
    print(f"   Lote:    {DATA_LOTE}")
    print(f"   Destino: {OUT_DIR.resolve()}")
    print(f"   Total:   {len(ARQUIVOS)} arquivos")
    print("   ⚠️  Isso pode levar horas dependendo da sua internet.")
    print("=" * 60)

    ok    = 0
    falhas = []

    for i, nome in enumerate(ARQUIVOS, 1):
        print(f"\n[{i}/{len(ARQUIVOS)}] {nome}")

        # Baixa
        if not baixar_arquivo(nome):
            falhas.append(nome)
            continue

        # Descompacta se o ZIP existir
        zip_path = OUT_DIR / f"{nome}.zip"
        if zip_path.exists():
            if not descompactar(nome):
                falhas.append(nome)
                continue

        ok += 1

    # ── Resumo ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📋 RESUMO DO DOWNLOAD")
    print(f"   Sucesso:  {ok}")
    print(f"   Falhas:   {len(falhas)}")
    if falhas:
        print("   Arquivos com falha:")
        for f in falhas:
            print(f"     - {f}")
    print("=" * 60)

    if ok > 0:
        csvs = list(OUT_DIR.glob("*"))
        print(f"\n✅ {len(csvs)} arquivo(s) prontos em {OUT_DIR}/")
        print("   Próximo passo: python pipeline/01_import_empresas.py")
    else:
        print("\n❌ Nenhum arquivo baixado com sucesso.")
        sys.exit(1)

if __name__ == "__main__":
    main()