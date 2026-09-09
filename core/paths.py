"""
Gestion centralisée des chemins du projet.
Fournit des constantes fiables pour tous les dossiers critiques.
"""

import os
import platform
import sys
from pathlib import Path


class Paths:
    """Singleton de gestion des chemins du projet"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 🔍 Détection automatique du root projet
        self.PROJECT_ROOT = Path(__file__).parent.parent.resolve()
        
        # 📂 Dossiers principaux
        self.CONFIG = self.PROJECT_ROOT / "config"
        self.LIBRARIES = self.PROJECT_ROOT / "libraries"
        self.TEST_SUITES = self.PROJECT_ROOT / "test_suites"
        self.TOOLS = self.PROJECT_ROOT / "tools"
        self.API = self.PROJECT_ROOT / "api"
        self.UI = self.PROJECT_ROOT / "testops"
        
        # 📂 Sous-dossiers libraries
        self.RESOURCES = self.LIBRARIES / "resources"
        self.TEST_DATA = self.LIBRARIES / "test_data"
        self.TEST_OBJECTS = self.LIBRARIES / "test_objects"

        # 📂 Rapports générés (index, artefacts de run)
        self.RESULTS = self.PROJECT_ROOT / "results"
        
        # 📂 Dossiers de sortie (dépendent de l'OS)
        if platform.system() == "Darwin":  # macOS
            self.OUTPUT_ROOT = Path.home() / "rf_output"
        else:  # Windows
            self.OUTPUT_ROOT = Path(os.path.expanduser("~")) / "rf_output"
        
        self.REPORTS = self.OUTPUT_ROOT / "report"
        
        # 📂 Créer les dossiers si nécessaires
        self.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        self.REPORTS.mkdir(parents=True, exist_ok=True)

        # 📂 Dossier temp pour fichiers temporaires
        self.TEMP = self.PROJECT_ROOT / "temp"
        self.TEMP.mkdir(parents=True, exist_ok=True)
        
        # 🛑 Fichier de signal d'arrêt (PARTAGÉ)
        self.STOP_SIGNAL = self.TEMP / "stop_signal.txt"
        
        # ✅ CONFIGURER LE PYTHONPATH
        self._setup_pythonpath()
        
        self._initialized = True
    
    def _setup_pythonpath(self):
        """
        Configure le PYTHONPATH pour que tous les imports fonctionnent.
        """
        critical_paths = [
            str(self.PROJECT_ROOT),
            str(self.LIBRARIES),
        ]
        
        for path in critical_paths:
            if path not in sys.path:
                sys.path.insert(0, path)
        
        current_pythonpath = os.environ.get('PYTHONPATH', '')
        separator = os.pathsep
        
        missing_paths = [p for p in critical_paths if p not in current_pythonpath]
        
        if missing_paths:
            if current_pythonpath:
                os.environ['PYTHONPATH'] = separator.join(missing_paths + [current_pythonpath])
            else:
                os.environ['PYTHONPATH'] = separator.join(missing_paths)
    
    def get_report_folder(self, dt_stamp):
        """Retourne le chemin du dossier de rapport pour un timestamp donné"""
        return self.REPORTS / dt_stamp
    
    def get_merge_dir(self, dt_stamp):
        """Retourne le chemin du dossier de fusion"""
        return self.get_report_folder(dt_stamp) / "Output_merge"
    
    def get_output_xml(self, dt_stamp, merged=False):
        """Retourne le chemin du fichier output.xml"""
        if merged:
            return self.get_report_folder(dt_stamp) / "Output_merge" / "output_merge.xml"
        return self.get_report_folder(dt_stamp) / "Output_original" / "output_original.xml"
    
    def __str__(self):
        """Affichage lisible des chemins"""
        return f"""
Paths Configuration:
  PROJECT_ROOT: {self.PROJECT_ROOT}
  LIBRARIES:    {self.LIBRARIES}
  OUTPUT_ROOT:  {self.OUTPUT_ROOT}
  REPORTS:      {self.REPORTS}
"""


# Instance globale
paths = Paths()
