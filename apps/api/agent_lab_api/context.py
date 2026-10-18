from .conversation_models import PromptMessage, Turn

SYSTEM_PROMPT = (
    "你是以尊重與溝通為核心的戀愛諮詢助手。先理解使用者是單身、交往或已婚，"
    "釐清事情經過、雙方反應與使用者的期待，再提出具體、尊重界線的小步驟。"
    "資訊不足時先問問題，不捏造對方想法，不宣稱心理診斷。"
    "使用者更正條件時，只依最新條件回答，不再提已被更正的地點或預算。"
    "你沒有即時的店家、價格或交通資料：不寫任何店家、景點、場館、車站或路線的專有名稱，"
    "也不寫具體價格；只用類型描述（例如「公共圖書館」「全素小吃店」），"
    "給預算分配比例與使用者可自行查證的關鍵字。使用繁體中文。"
)
MAX_CONTEXT_TURNS = 6
MAX_CONTEXT_CHARS = 24000


def build_context(turns: list[Turn], question: str | None = None) -> list[PromptMessage]:
    current = [PromptMessage(role="user", content=question)] if question is not None else []
    budget = MAX_CONTEXT_CHARS - len(SYSTEM_PROMPT) - sum(len(m.content) for m in current)
    selected: list[list[PromptMessage]] = []
    completed = [turn for turn in turns if turn.status == "completed"]
    for turn in reversed(completed[-MAX_CONTEXT_TURNS:]):
        size = len(turn.question) + len(turn.answer)
        if size > budget:
            break
        budget -= size
        selected.append(
            [
                PromptMessage(role="user", content=turn.question),
                PromptMessage(role="assistant", content=turn.answer),
            ]
        )
    return [
        PromptMessage(role="system", content=SYSTEM_PROMPT),
        *(message for pair in reversed(selected) for message in pair),
        *current,
    ]
