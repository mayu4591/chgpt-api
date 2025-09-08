import requests
import json

# 基本的なチャット補完テスト
print("=== 基本チャットテスト ===")
try:
    response = requests.post(
        "http://localhost:8000/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, please respond with just 'Hi there!'"}
            ],
            "max_tokens": 50
        },
        timeout=30
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {data['choices'][0]['message']['content']}")
    else:
        print(f"Error: {response.text}")

except Exception as e:
    print(f"Request failed: {e}")

print("\n=== Function Calling テスト ===")
try:
    # Function Callingテスト
    function_response = requests.post(
        "http://localhost:8000/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "What's the weather like in Tokyo? Please use the get_weather function."}
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
        },
        timeout=60
    )

    print(f"Status: {function_response.status_code}")
    if function_response.status_code == 200:
        result = function_response.json()
        print(f"Response structure: {list(result.keys())}")
        if 'choices' in result and result['choices']:
            choice = result['choices'][0]
            if 'message' in choice:
                message = choice['message']
                print(f"Message role: {message.get('role')}")
                print(f"Message content: {message.get('content')}")
                print(f"Function call: {message.get('function_call')}")
                print(f"Finish reason: {choice.get('finish_reason')}")
    else:
        print(f"Error: {function_response.text}")

except Exception as e:
    print(f"Function calling test failed: {e}")
