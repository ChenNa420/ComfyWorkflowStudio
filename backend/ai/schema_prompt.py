import json
from .models import SemanticAnalysis, AdaptedStory, Episode, PageDialogueResult, PageVisualResult

SCHEMAS = {
    'semantic': SemanticAnalysis.model_json_schema(),
    'adapted_story': AdaptedStory.model_json_schema(),
    'episode': Episode.model_json_schema(),
    'page_dialogue': PageDialogueResult.model_json_schema(),
    'page_visual': PageVisualResult.model_json_schema(),
}

def schema_instruction(name: str) -> str:
    return 'Return JSON matching this schema exactly:\n' + json.dumps(SCHEMAS[name], ensure_ascii=False)
