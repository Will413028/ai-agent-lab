import json
from pathlib import Path

from agent_lab_api.contracts import EVENT_ADAPTER
from agent_lab_api.conversation_models import ApiModels
from agent_lab_api.image_models import ImageModels
from agent_lab_api.main import app
from agent_lab_api.rag_models import RagModels
from agent_lab_api.run_models import RunModels
from agent_lab_api.tool_models import ToolModels

root = Path(__file__).resolve().parents[2]
target = root / "contracts"
target.mkdir(exist_ok=True)
schema = EVENT_ADAPTER.json_schema()
schema["title"] = "ChatEvent"
(target / "chat-event.schema.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
)
(target / "openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
(target / "conversation.schema.json").write_text(
    json.dumps(ApiModels.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
(target / "rag.schema.json").write_text(
    json.dumps(RagModels.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
(target / "tools.schema.json").write_text(
    json.dumps(ToolModels.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
(target / "images.schema.json").write_text(
    json.dumps(ImageModels.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
(target / "runs.schema.json").write_text(
    json.dumps(RunModels.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
