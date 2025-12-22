# qrane/paths.py - Centralized Path Management
from pathlib import Path

class PathManager:
    """
    Manages all file and directory paths for a QonQrete run.
    Ensures consistency and simplifies path construction logic.
    """
    def __init__(self, worqspace_root: Path):
        self.root = worqspace_root

    @property
    def struqture_dir(self) -> Path:
        return self.root / "struqture"

    @property
    def qodeyard_dir(self) -> Path:
        return self.root / "qodeyard"

    @property
    def qontext_dir(self) -> Path:
        return self.root / "qontext.d"

    @property
    def bloq_dir(self) -> Path:
        return self.root / "bloq.d"

    @property
    def qache_dir(self) -> Path:
        return self.root / "sqrapyard" / "qache.d"

    def get_tasq_dir(self) -> Path:
        return self.root / "tasq.d"

    def get_briq_dir(self) -> Path:
        return self.root / "briq.d"

    def get_exeq_dir(self) -> Path:
        return self.root / "exeq.d"

    def get_reqap_dir(self) -> Path:
        return self.root / "reqap.d"

    def get_tasq_path(self, cycle: int) -> Path:
        return self.get_tasq_dir() / f"cyqle{cycle}_tasq.md"

    def get_summary_path(self, cycle: int) -> Path:
        return self.get_exeq_dir() / f"cyqle{cycle}_summary.md"

    def get_reqap_path(self, cycle: int) -> Path:
        return self.get_reqap_dir() / f"cyqle{cycle}_reqap.md"

    def get_qonsole_log_path(self, agent_name: str) -> Path:
        log_dir = self.struqture_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"qonsole_{agent_name}.log"

    def get_events_log_path(self, agent_name: str) -> Path:
        log_dir = self.struqture_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"events_{agent_name}.log"
