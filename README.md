# ChatGPT Selenium API

SeleniumWebDriverを使用してブラウザ上のChatGPTを制御し、OpenAI互換のREST APIとして提供するツール

## 概要

このツールは以下の機能を提供します：
- SeleniumによるChatGPTブラウザ制御
- OpenAI Chat Completions API互換のREST API
- 複数ブラウザサポート（Chrome、Firefox）
- ヘッドレス・ヘッドフルモード対応

## インストール

1. 依存関係のインストール:
```bash
pip install -r requirements.txt
```

2. ChromeDriverの準備:
- 初回実行時にWebDriverManagerが自動ダウンロード
- Selenium 4.15.2に対応したWebDriverを使用
- Chrome ブラウザが事前にインストールされている必要があります

**注意**: WebDriverManagerによる自動ダウンロードでエラーが発生する場合は、手動でChromeDriverをダウンロードし、PATHに追加してください。

## 使用方法

### 基本的な起動

```bash
python main.py
```

**重要**: Chromeブラウザは最初のAPI呼び出し時に自動的に起動されます。起動後はバックグラウンドで動作し、リモートデバッグモードで制御されます。

### Chrome起動状態の確認

Chrome の起動状態は以下のエンドポイントで確認できます：

```bash
curl http://localhost:8000/v1/chrome/status
```

レスポンス例：
```json
{
  "chrome_status": "active",
  "message": "Chrome is running and ready for requests",
  "timestamp": 1757255560
}
```

### 設定オプション

環境変数で設定可能：

- `BROWSER_TYPE`: ブラウザタイプ（chrome/firefox、デフォルト：chrome）
- `HEADLESS`: ヘッドレスモード（true/false、デフォルト：false）
- `TIMEOUT`: タイムアウト秒数（デフォルト：30）
- `PORT`: APIサーバーポート（デフォルト：8000）
- `CHATGPT_URL`: ChatGPTのURL（デフォルト：https://chat.openai.com）

### API使用例

```python
import requests

# 基本的なチャット補完
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "Hello, world!"}
        ],
        "max_tokens": 100
    }
)

print(response.json())

# Function Callingの使用例
def get_weather(location, unit="celsius"):
    # 実際の天気情報取得ロジック
    return f"The weather in {location} is 22°{unit.upper()}"

# Function定義付きリクエスト
function_response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "What's the weather like in Tokyo? Please use the get_weather function to check."}
        ],
        "functions": [
            {
                "name": "get_weather",
                "description": "Get the current weather in a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA"
                        },
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location"]
                }
            }
        ],
        "function_call": "auto"
    }
)

result = function_response.json()

# Function callが正常に処理された場合
if function_response.status_code == 200:
    choice = result["choices"][0]

    # Function callが検出された場合
    if choice["message"].get("function_call"):
        function_name = choice["message"]["function_call"]["name"]
        function_args = json.loads(choice["message"]["function_call"]["arguments"])

        # 実際の関数実行
        if function_name == "get_weather":
            weather_result = get_weather(**function_args)

            # Function結果を含めて再度リクエスト
            final_response = requests.post(
                "http://localhost:8000/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "user", "content": "What's the weather like in Tokyo?"},
                        {
                            "role": "assistant",
                            "content": None,
                            "function_call": {
                                "name": "get_weather",
                                "arguments": json.dumps(function_args)
                            }
                        },
                        {
                            "role": "function",
                            "name": "get_weather",
                            "content": weather_result
                        }
                    ]
                }
            )
            print(final_response.json())
    else:
        # Function callが検出されなかった場合（通常の応答）
        print("ChatGPT responded without function call:")
        print(choice["message"]["content"])
else:
    print(f"Error: {result}")
```

## API仕様

### Chat Completions API

- **Endpoint**: `POST /v1/chat/completions`
- **説明**: ChatGPTとチャット対話を行います。Function Calling機能もサポートしています。

**基本リクエスト例**:
```json
{
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
}
```

**Function Callingリクエスト例**:
```json
{
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "user", "content": "What's the weather like in Tokyo?"}
    ],
    "functions": [
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    },
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            }
        }
    ],
    "function_call": "auto"
}
```

**レスポンス例**:
```json
{
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "gpt-3.5-turbo",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "Hello! How can I help you today?"
        },
        "finish_reason": "stop"
    }],
    "usage": {
        "prompt_tokens": 9,
        "completion_tokens": 12,
        "total_tokens": 21
    }
}
```

**Function Callレスポンス例**:
```json
{
    "id": "chatcmpl-456",
    "object": "chat.completion",
    "created": 1677652290,
    "model": "gpt-3.5-turbo",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": null,
            "function_call": {
                "name": "get_weather",
                "arguments": "{\"location\": \"Tokyo, Japan\", \"unit\": \"celsius\"}"
            }
        },
        "finish_reason": "function_call"
    }],
    "usage": {
        "prompt_tokens": 82,
        "completion_tokens": 18,
        "total_tokens": 100
    }
}
```

### Models API

- **Endpoint**: `GET /v1/models`
- **説明**: 利用可能なモデル一覧を取得します

### Health Check

- **Endpoint**: `GET /health`
- **説明**: サービスの稼働状況を確認します

## アーキテクチャ

```
├── main.py              # アプリケーションエントリポイント
├── api/                 # REST APIエンドポイント
├── services/            # ビジネスロジック
├── drivers/             # WebDriverラッパー
├── models/              # データモデル
├── config/              # 設定管理
├── utils/               # ユーティリティ
└── tests/               # テストコード
```

## 注意事項・制限事項

### 一般的な制限事項
- ChatGPTのWebインターフェースの変更により動作しなくなる可能性があります
- ブラウザの自動化検知により制限される場合があります
- 長時間の利用時はセッション管理に注意してください

### Function Calling に関する制限事項
- **重要**: このツールはChatGPTのブラウザ版を使用するため、OpenAI APIのようなネイティブFunction Callingはサポートされていません
- Function Callingはプロンプトエンジニアリングによる疑似的な実装です
- ChatGPTが関数呼び出し指示を理解しない場合があります
- 複雑な関数定義や多数の関数は正しく処理されない可能性があります
- Function Call応答のJSON形式が不正な場合、通常の会話として処理されます

### 推奨事項
- Function Calling を使用する場合は、シンプルな関数定義を使用してください
- Function Calling に依存しない代替ロジックを用意することを推奨します
- 本格的なFunction Calling機能が必要な場合は、OpenAI公式APIの使用を検討してください

## ライセンス

MIT License
