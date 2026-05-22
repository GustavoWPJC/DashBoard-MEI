# scheduler/atualizar_mensal.py
# Automação mensal — roda o pipeline completo automaticamente
#
# Duas formas de usar:
#
# 1) Rodar manualmente uma vez:
#       python scheduler/atualizar_mensal.py --agora
#
# 2) Deixar rodando em background (executa todo dia 1º do mês às 06:00):
#       python scheduler/atualizar_mensal.py
#
# 3) Agendar via cron do Linux (recomendado para produção):
#       crontab -e
#       0 6 1 * * /caminho/do/projeto/venv/bin/python /caminho/do/projeto/scheduler/atualizar_mensal.py --agora

import sys
import subprocess
import logging
from datetime import datetime
from pathlib import Path

import schedule
import time

# ── Configurações ──────────────────────────────────────────────────────────
# Ordem exata de execução do pipeline completo
PIPELINE = [
    ("Importar Empresas (RFB)",          "pipeline/01_import_empresas.py"),
    ("Importar Estabelecimentos (RFB)",  "pipeline/02_import_estabelecimentos.py"),
    ("Importar Simples Nacional (RFB)",  "pipeline/03_import_simples.py"),
    ("Construir base MEI ativo",         "pipeline/04_create_mei_ativo.py"),
    ("Coletar contratos PNCP",           "pipeline/05_pncp_coleta_contratos.py"),
    ("Cruzar PNCP com MEI + KPIs",       "pipeline/06_pncp_join_mei.py"),
    ("Gerar gráficos e relatório HTML",  "analysis/07_plot_kpis.py"),
]

# Pasta de logs
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ── Logger ─────────────────────────────────────────────────────────────────
def get_logger() -> logging.Logger:
    """Configura o logger para gravar no arquivo e no terminal ao mesmo tempo."""
    log_file = LOG_DIR / f"atualizacao_{datetime.now().strftime('%Y%m')}.log"

    logger = logging.getLogger("memp")
    logger.setLevel(logging.INFO)

    # Evita duplicar handlers se chamar mais de uma vez
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # Handler de arquivo
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)

    # Handler de terminal
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger

# ── Execução de um script ──────────────────────────────────────────────────
def rodar_script(nome: str, caminho: str, logger: logging.Logger) -> bool:
    """
    Roda um script Python como subprocesso.
    Retorna True se concluiu sem erro, False se falhou.
    """
    logger.info(f"▶  Iniciando: {nome}")
    inicio = datetime.now()

    try:
        resultado = subprocess.run(
            [sys.executable, caminho],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        duracao = (datetime.now() - inicio).seconds

        # Imprime stdout do script no log
        if resultado.stdout.strip():
            for linha in resultado.stdout.strip().splitlines():
                logger.info(f"   {linha}")

        if resultado.returncode != 0:
            logger.error(f"❌ FALHOU ({duracao}s): {nome}")
            if resultado.stderr.strip():
                for linha in resultado.stderr.strip().splitlines():
                    logger.error(f"   STDERR: {linha}")
            return False

        logger.info(f"✅ Concluído ({duracao}s): {nome}")
        return True

    except Exception as e:
        logger.error(f"❌ Exceção ao rodar {nome}: {e}")
        return False

# ── Pipeline completo ──────────────────────────────────────────────────────
def rodar_pipeline():
    """Executa todos os scripts do pipeline em ordem."""
    logger = get_logger()

    logger.info("=" * 60)
    logger.info("🚀 INÍCIO DA ATUALIZAÇÃO MENSAL — PROJETO MEMP")
    logger.info(f"   Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info("=" * 60)

    total   = len(PIPELINE)
    ok      = 0
    falhas  = []

    for i, (nome, caminho) in enumerate(PIPELINE, 1):
        logger.info(f"\n[{i}/{total}] {nome}")

        sucesso = rodar_script(nome, caminho, logger)

        if sucesso:
            ok += 1
        else:
            falhas.append(nome)
            # Se um script de ingestão falhar, não tem sentido continuar
            # pois os próximos dependem dele
            if i <= 4:
                logger.error(
                    f"\n⛔ Script crítico falhou ({nome}). "
                    f"Abortando pipeline para evitar dados inconsistentes."
                )
                break

    # ── Resumo final ───────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("📋 RESUMO DA ATUALIZAÇÃO")
    logger.info(f"   Scripts executados: {i} de {total}")
    logger.info(f"   Sucessos:           {ok}")
    logger.info(f"   Falhas:             {len(falhas)}")

    if falhas:
        logger.error("   Scripts com falha:")
        for f in falhas:
            logger.error(f"     - {f}")
        logger.error("❌ Atualização concluída COM ERROS.")
    else:
        logger.info("✅ Atualização concluída com SUCESSO!")

    logger.info("=" * 60)

# ── Agendador mensal ───────────────────────────────────────────────────────
def iniciar_agendador():
    """
    Agenda o pipeline para rodar todo dia 1º do mês às 06:00.
    Fica em loop aguardando — use Ctrl+C para parar.
    """
    logger = get_logger()

    # O schedule não tem "todo dia 1º do mês" nativo,
    # então agendamos diariamente e verificamos se é dia 1
    def verificar_e_rodar():
        if datetime.now().day == 1:
            rodar_pipeline()

    schedule.every().day.at("06:00").do(verificar_e_rodar)

    logger.info("⏰ Agendador iniciado — pipeline roda todo dia 1º do mês às 06:00")
    logger.info("   Pressione Ctrl+C para parar.")
    logger.info(f"   Próxima verificação: amanhã às 06:00")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # verifica a cada minuto
    except KeyboardInterrupt:
        logger.info("\n⏹  Agendador encerrado pelo usuário.")

# ── Main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # --agora → roda o pipeline imediatamente (sem agendar)
    if "--agora" in sys.argv:
        rodar_pipeline()
    else:
        iniciar_agendador()