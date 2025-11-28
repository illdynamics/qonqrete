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

    def get_agent_log_path(self, cycle: int, agent_name: str) -> Path:
        return self.struqture_dir / f"cyqle{cycle}_{agent_name}.log"
