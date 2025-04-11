import logging 


############# TAKE THESE VALUES FROM ENV FILE
def setup_logger(name: str, log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    import logging
    from logging.handlers import RotatingFileHandler
    """
    Sets up a logger with a given name and configuration.

    Args:
        name (str): The name of the logger.
        log_file (str): The file to log messages to. Defaults to 'app.log'.
        level (int): The logging level (e.g., logging.INFO, logging.DEBUG). Defaults to logging.INFO.

    Returns:
        logging.Logger: Configured logger instance.
    """
    # Create a logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Check if the logger already has handlers to avoid duplicate logs
    if not logger.handlers:
        # Create a file handler with log rotation
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
        file_handler.setLevel(level)

        # Create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        # Create a formatter and set it for both handlers
        formatter = logging.Formatter(
            "%(levelname)s - %(asctime)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
