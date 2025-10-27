from tqdm import tqdm
import yaml
import os
import argparse
import time
from utils.utilities import partition, get_image_count
from copy import deepcopy
from multiprocessing import Process, Manager
import multiprocessing as mp
import logging
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # Disable the warning

class ConfigHandler:
    """Centralized configuration management with validation"""
    
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self._validate_paths()
        self._normalize_device_config()

    def _load_config(self, path: str) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file {path} not found")
            
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _validate_paths(self):
        required_paths = [
            ('paths.document_root', True)
        ]
        
        for path, check_existence in required_paths:
            parts = path.split('.')
            value = self.config
            for part in parts:
                value = value.get(part)
                if value is None:
                    raise ValueError(f"Missing config key: {path}")
                    
            if check_existence and not os.path.exists(value):
                raise FileNotFoundError(f"Path {value} not found")

    def _normalize_device_config(self):
        """Ensure device configuration is always a list"""
        detector_config = self.config['detectors']['hi_sam_detector']
        devices = detector_config.get('devices')
        
        if not devices:
            single_device = detector_config.get('device', 'cuda:0')
            detector_config['devices'] = [single_device]
        elif isinstance(devices, str):
            detector_config['devices'] = [devices]

class DocumentProcessor:
    """Main processing orchestrator"""
    def __init__(self, config_path: str = "config.yaml", override_path: str = None):
        self.config_handler = ConfigHandler(config_path)
        self.config = self.config_handler.config

        if override_path:
            self.config["paths"]["document_root"] = override_path

        self.logger = LoggingManager(self.config["logging"])

        # If layout to be processed
        if self.config["layout"]["process"]:
            from utils.layout import LayoutExtractor
            extractor = LayoutExtractor(self.config)
            extractor.preprocess()

    def process(self, args):
        """Main entry point"""
        if args.det_mode == "hisam":
            self._run_detection_hisam(args)
        if args.det_mode == "hisam_cs":
            self._run_detection_hisam_cs(args)
        if args.det_mode == "surya":
            self._run_detection_surya(args)
        if args.det_mode == 'ensemble':
            self.ensemble(args)
        elif args.rec_mode:
            self._run_recognition(args)



    def _run_detection_hisam_cs(self, args):
        from detectors.models.hisam_cs_infer import HiSAMDetector
        hisam_detector = HiSAMDetector(self.config["detectors"]["hi_sam_detector"])
        hisam_detector.detect(self.config['paths']['document_root'])

import logging

class LoggingManager:
    """
    Unified Logging configuration
    """
    def __init__(self, logging_config: dict):
        """
        Initializes the LoggingManager with a given configuration.

        Args:
            logging_config (dict): A dictionary containing logigng configuration parameters.
        """
        self.log_path = logging_config["path"]
        self.log_level = logging_config["level"]

    def _configure_logging(self):
        """
        Configures the logging parameters
        """
        logging.basicConfig(
            filename=self.log_path,
            level=getattr(logging, self.log_level, logging.INFO),
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            force=True
        )
        logging.captureWarnings(True)
if __name__ == "__main__":
    CONFIG_PATH = "config.yaml"

    import warnings
    warnings.filterwarnings("ignore")

    start_time = time.time()

    parser = argparse.ArgumentParser(description="Run either HiSAMDetector or Suryaa OCR")
    parser.add_argument("--det_mode", choices=["hisam", "hisam_cs", "surya", "ensemble"], required=False)
    parser.add_argument("--target_dir", type=str, required=False, help="Override 'paths.document_root' from config file for this specific run.")
    parser.add_argument("--rec_mode", choices=["recognizer"], required=False)
    parser.add_argument("--start", type=int, required=False)
    parser.add_argument("--end", type=int, required=False)
    args = parser.parse_args()

    mp.set_start_method("spawn", force=True)

    # 1. Load the YAML config
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file {CONFIG_PATH} not found.")

    with open(CONFIG_PATH, 'r') as f:
        config_all = yaml.safe_load(f)

    processor = DocumentProcessor(override_path=args.target_dir)
    processor.process(args)