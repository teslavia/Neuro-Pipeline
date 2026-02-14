"""Health check probes — liveness and readiness."""

from dataclasses import dataclass, field


@dataclass
class HealthStatus:
    alive: bool = True
    ready: bool = False
    checks: dict[str, bool] = field(default_factory=dict)


class HealthChecker:
    """Provides liveness and readiness probes."""

    def __init__(self, orchestrator=None, store=None, server=None):
        self._orchestrator = orchestrator
        self._store = store
        self._server = server

    def liveness(self) -> HealthStatus:
        """Process is alive — always True if we can execute this."""
        return HealthStatus(alive=True, ready=True, checks={"process": True})

    def readiness(self) -> HealthStatus:
        """All subsystems ready to accept traffic."""
        checks: dict[str, bool] = {}

        # Model loaded?
        checks["model_loaded"] = (
            self._orchestrator is not None
            and self._orchestrator.inference_engine is not None
            and getattr(self._orchestrator.inference_engine, "_loaded", False)
        )

        # DB connected?
        checks["db_connected"] = (
            self._store is not None
            and getattr(self._store, "_conn", None) is not None
        )

        # gRPC serving?
        checks["grpc_serving"] = (
            self._server is not None
            and getattr(self._server, "server", None) is not None
        )

        ready = all(checks.values())
        return HealthStatus(alive=True, ready=ready, checks=checks)
