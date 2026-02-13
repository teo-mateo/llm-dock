from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class BenchmarkRun:
    id: str
    service_name: str
    model_path: str
    status: str = "pending"
    params_json: Dict[str, str] = field(default_factory=dict)

    pp_avg_ts: Optional[float] = None
    pp_stddev_ts: Optional[float] = None
    tg_avg_ts: Optional[float] = None
    tg_stddev_ts: Optional[float] = None

    raw_output: Optional[str] = None
    error_message: Optional[str] = None

    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    build_commit: Optional[str] = None
    model_type: Optional[str] = None
    model_size: Optional[int] = None
    model_n_params: Optional[int] = None
    gpu_info: Optional[str] = None
    cpu_info: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "model_path": self.model_path,
            "status": self.status,
            "params": self.params_json,
            "pp_avg_ts": self.pp_avg_ts,
            "pp_stddev_ts": self.pp_stddev_ts,
            "tg_avg_ts": self.tg_avg_ts,
            "tg_stddev_ts": self.tg_stddev_ts,
            "raw_output": self.raw_output,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "build_commit": self.build_commit,
            "model_type": self.model_type,
            "model_size": self.model_size,
            "model_n_params": self.model_n_params,
            "gpu_info": self.gpu_info,
            "cpu_info": self.cpu_info,
        }

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "model_path": self.model_path,
            "status": self.status,
            "params": self.params_json,
            "pp_avg_ts": self.pp_avg_ts,
            "tg_avg_ts": self.tg_avg_ts,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
