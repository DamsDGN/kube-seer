"""
Point d'entrée principal de l'agent SRE
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path

import structlog

# Ajouter le répertoire src au path Python
src_path = Path(__file__).parent.absolute()
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from config import Config  # noqa: E402
from agent import SREAgent  # noqa: E402


def setup_logging(config: Config):
    """Configure le logging structuré"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configuration du niveau de log
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


async def main():
    """Point d'entrée principal"""
    print("🚀 Démarrage de l'agent IA SRE EFK...")

    try:
        # Charger la configuration
        config = Config()

        # Configurer le logging
        setup_logging(config)
        logger = structlog.get_logger()

        logger.info(
            "Configuration chargée",
            config={
                "elasticsearch_url": config.elasticsearch_url,
                "analysis_interval": config.analysis_interval,
                "log_level": config.log_level,
            },
        )

        # Créer l'agent
        agent = SREAgent(config)

        # Gestionnaire d'arrêt propre
        def signal_handler(signum, frame):
            logger.info("Signal d'arrêt reçu", signal=signum)
            asyncio.create_task(agent.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Démarrer l'agent
        logger.info("🤖 Agent SRE démarré - Analyse de la stack EFK en cours...")
        await agent.start()

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error("Erreur fatale", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        logger.info("🛑 Agent SRE arrêté")


if __name__ == "__main__":
    asyncio.run(main())
