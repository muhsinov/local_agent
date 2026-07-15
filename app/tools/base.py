from app.agent.models import ToolDefinition


class ReadOnlyTool:
    input_model = None

    def __init__(self, *, name: str, description: str, timeout_seconds: int) -> None:
        self.definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=self.input_model.model_json_schema(),
            read_only=True,
            requires_approval=False,
            write_effect=False,
            timeout_seconds=timeout_seconds,
        )

    def execute(self, arguments, settings) -> str:
        raise NotImplementedError

    async def execute_async(self, arguments, settings) -> str:
        return self.execute(arguments, settings)


class ApprovalRequiredTool:
    input_model = None

    def __init__(self, *, name: str, description: str, timeout_seconds: int) -> None:
        self.definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=self.input_model.model_json_schema(),
            read_only=False,
            requires_approval=True,
            write_effect=True,
            timeout_seconds=timeout_seconds,
        )

    def build_safe_summary(self, arguments) -> str:
        raise NotImplementedError

    async def execute_with_approval(self, arguments, settings, **kwargs) -> str:
        raise NotImplementedError
