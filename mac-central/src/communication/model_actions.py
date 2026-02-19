"""Strategy pattern for model management actions — replaces 5 if-else branches in ManageModel."""

from src.core.logging import get_logger

logger = get_logger(__name__)


class ModelActionHandler:
    """Dispatches model management actions to handler methods."""

    def __init__(self, model_registry, pb_module):
        self._registry = model_registry
        self._pb = pb_module
        self._handlers = {
            pb_module.ModelManagementRequest.DEPLOY: self._deploy,
            pb_module.ModelManagementRequest.UNDEPLOY: self._undeploy,
            pb_module.ModelManagementRequest.LIST: self._list,
            pb_module.ModelManagementRequest.ROLLBACK: self._rollback,
            pb_module.ModelManagementRequest.STATUS: self._status,
        }

    async def handle(self, request):
        """Handle a ModelManagementRequest, return ModelManagementResponse."""
        handler = self._handlers.get(request.action)
        if handler is None:
            return self._pb.ModelManagementResponse(
                success=False, message=f"Unknown action: {request.action}"
            )
        return await handler(request)

    async def _deploy(self, request):
        model = request.model
        ok = self._registry.deploy(
            model_id=model.model_id,
            model_path=model.model_path,
            model_type=model.model_type,
            version=model.version,
            target_device_id=request.target_device_id,
            npu_core=request.npu_core,
            metadata=dict(model.metadata),
        )
        return self._pb.ModelManagementResponse(
            success=ok, message="Deployed" if ok else "Deploy failed"
        )

    async def _undeploy(self, request):
        ok = self._registry.undeploy(request.model.model_id)
        return self._pb.ModelManagementResponse(
            success=ok, message="Undeployed" if ok else "Undeploy failed"
        )

    async def _list(self, request):
        records = self._registry.list_models(device_id=request.target_device_id)
        model_infos = [
            self._pb.ModelInfo(
                model_id=r.model_id, model_path=r.model_path,
                model_type=r.model_type, version=r.version,
                metadata=r.metadata,
            )
            for r in records
        ]
        return self._pb.ModelManagementResponse(
            success=True, message=f"{len(model_infos)} models", models=model_infos
        )

    async def _rollback(self, request):
        ok = self._registry.rollback(request.model.model_id)
        return self._pb.ModelManagementResponse(
            success=ok, message="Rolled back" if ok else "Rollback failed"
        )

    async def _status(self, request):
        record = self._registry.get_model(request.model.model_id)
        if not record:
            return self._pb.ModelManagementResponse(
                success=False, message="Model not found"
            )
        info = self._pb.ModelInfo(
            model_id=record.model_id, model_path=record.model_path,
            model_type=record.model_type, version=record.version,
            metadata={**record.metadata, "status": record.status.value},
        )
        return self._pb.ModelManagementResponse(
            success=True, message=record.status.value, models=[info]
        )
