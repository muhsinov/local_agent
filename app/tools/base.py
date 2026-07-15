from app.agent.models import ToolDefinition


class ReadOnlyTool:
    input_model = None

    def __init__(self, *, name: str, description: str, timeout_seconds: int) -> None:
        self.definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=self.input_model.model_json_schema(),
            read_only=True,
            timeout_seconds=timeout_seconds,
        )

    def execute(self, arguments, settings) -> str:
        raise NotImplementedError

    async def execute_async(self, arguments, settings) -> str:
        return self.execute(arguments, settings)
