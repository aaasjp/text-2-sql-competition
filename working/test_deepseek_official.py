from openai import OpenAI
client = OpenAI(api_key="sk-174d1f573c36449687b96198e94a911d", base_url="https://api.deepseek.com")

# Turn 1
messages = [{"role": "user", "content": "9.11 and 9.8, which is greater?"}]
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
print(f"Turn 1 reasoning: {response.choices[0].message.reasoning_content}")
print(f"Turn 1 content: {response.choices[0].message.content}")
reasoning_content = response.choices[0].message.reasoning_content
content = response.choices[0].message.content

# Turn 2
# The reasoning_content will be ignored by the API
messages.append(response.choices[0].message)
messages.append({'role': 'user', 'content': "How many Rs are there in the word 'strawberry'?"})
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=messages,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
print(f"Turn 2 reasoning: {response.choices[0].message.reasoning_content}")
print(f"Turn 2 content: {response.choices[0].message.content}")