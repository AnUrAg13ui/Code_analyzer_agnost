import logging
import logging.config
import sys
import os

def setup_logging():
    """Configure comprehensive logging for the application."""
    
    # Ensure logs directory exists if logging to file
    os.makedirs("logs", exist_ok=True)
    
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(funcName)s() - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "stream": sys.stdout
            },
            "file": {
                "level": "DEBUG",
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "filename": "logs/analyzer.log",
                "maxBytes": 10485760, # 10MB
                "backupCount": 5,
                "encoding": "utf8"
            }
        },
        "loggers": {
            "": { # Root logger
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": True
            },
            "app": {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False
            },
            "agents": {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False
            },
            "graph": {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False
            },
            "database": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "services": {
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": False
            },
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            }
        }
    }
    
    logging.config.dictConfig(log_config)

