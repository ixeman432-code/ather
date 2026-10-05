import os
from anthropic import Anthropic

client = Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"]
)

message = client.messages.create(
    model=os.environ["MODEL_CLAUDE"],
    max_tokens=100,
    messages=[
        {
            "role": "user",
            "content": "اكتب جملة عربية قصيرة جداً للاختبار."
        }
    ]
)

for block in message.content:
    if block.type == "text":
        print(block.text)