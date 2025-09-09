from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel


class FunctionCall(BaseModel):
    """Function Call モデル"""
    name: str
    arguments: str  # JSON文字列


class ToolCall(BaseModel):
    """Tool Call モデル"""
    id: str
    type: str  # "function"
    function: FunctionCall


class ChatMessage(BaseModel):
    """チャットメッセージモデル"""
    role: str  # "system", "user", "assistant", "function"
    content: Optional[str] = None
    name: Optional[str] = None  # function roleの場合の関数名
    function_call: Optional[FunctionCall] = None  # assistant roleでfunction callする場合
    tool_calls: Optional[List[ToolCall]] = None  # 新しいTools API対応


class FunctionParameter(BaseModel):
    """Function パラメータ定義モデル"""
    type: str
    description: Optional[str] = None
    enum: Optional[List[str]] = None


class FunctionDefinition(BaseModel):
    """Function 定義モデル"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema形式


class ToolDefinition(BaseModel):
    """Tool 定義モデル"""
    type: str  # "function"
    function: FunctionDefinition


class ChatCompletionRequest(BaseModel):
    """チャット補完リクエストモデル"""
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False
    # Function Calling関連
    functions: Optional[List[FunctionDefinition]] = None  # 旧API互換
    function_call: Optional[Union[str, Dict[str, str]]] = None  # "auto", "none", {"name": "function_name"}
    # Tools API (新しい方式)
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    # 追加パラメータ
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    n: Optional[int] = 1


class ChatCompletionChoice(BaseModel):
    """チャット補完の選択肢モデル"""
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    """チャット補完の使用量モデル"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """チャット補完レスポンスモデル"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ModelInfo(BaseModel):
    """モデル情報モデル"""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    """モデル一覧レスポンスモデル"""
    object: str = "list"
    data: List[ModelInfo]


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンスモデル"""
    status: str
    timestamp: int


class ChatCompletionChunk(BaseModel):
    """ストリーミング用チャット補完チャンクモデル"""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]


class StreamingResponse(BaseModel):
    """ストリーミングレスポンス管理モデル"""
    content: str
    chunk_size: int = 20  # 文字単位でのチャンクサイズ
