# -----------------------------------------------------------

# GPT Scene Abstraction Script
# Requires: openai >= 1.0.0
# Usage: python script.py <input_file(.jsonl)> [<text_field>] [<keyword_field>]

# ------------------------- Imports -------------------------

import os
import sys
import json
import time
import copy
from typing import List

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from tqdm import tqdm

# ------------------------- Globals -------------------------

total_prompt_tokens_used = 0
total_completion_tokens_used = 0

# ------------------------- Token Cost Estimation -------------------------

def estimate_cost_gpt(model: str, price_input: float, price_output: float):
    """Estimate token cost based on usage."""
    cost = (total_prompt_tokens_used / 1000) * price_input + \
           (total_completion_tokens_used / 1000) * price_output
    print(f"\nModel name: {model}")
    print(f"Total input tokens used: {total_prompt_tokens_used}")
    print(f"Total output tokens used: {total_completion_tokens_used}")
    print(f"Estimated cost: ${cost:.4f}")
    return cost

# ------------------------- Output Validation -------------------------

def is_answer_acceptable(answer: str) -> bool:
    """Check if GPT output contains all required sections."""
    required_sections = [
        "**Scene Overview:**",
        "**Events:**",
        "**Entities:**",
        "**Setting:**",
        "**Scene Profile:**"
    ]
    return all(section in answer for section in required_sections)

# ------------------------- ICL Loader -------------------------

def load_icl_messages(instruction_path: str, icl_path: str) -> List[dict]:
    """Load system instruction and ICL messages."""
    messages = []

    with open(instruction_path, "r", encoding="utf-8") as f:
        messages.append({"role": "system", "content": f.read().strip()})

    with open(icl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry["role"] == "assistant" and isinstance(entry["content"], str):
                    try:
                        decoded = json.loads(entry["content"])
                        if isinstance(decoded, str):
                            entry["content"] = decoded
                    except json.JSONDecodeError:
                        pass
                messages.append(entry)
            except json.JSONDecodeError as e:
                print(f"⚠️ JSONDecodeError: {e} in line: {line}")
                raise
    return messages

# ------------------------- GPT Call -------------------------

def ask_gpt(
    client: OpenAI,
    row: dict,
    text_field: str,
    keyword_field: str,
    icl_messages: List[dict],
    gpt_model: str = "gpt-4o-mini",
    max_retries: int = 5,
    delay: int = 2
) -> str | bool:
    """Query GPT model with retries and fallback."""
    global total_prompt_tokens_used, total_completion_tokens_used

    for attempt in range(max_retries):
        try:
            messages = copy.deepcopy(icl_messages)
            prompt = row[text_field].strip() + " [KEYWORD] " + row[keyword_field].strip()
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=gpt_model,
                messages=messages,
                temperature=0.2,
                max_tokens=512,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )

            usage = response.usage
            total_prompt_tokens_used += usage.prompt_tokens
            total_completion_tokens_used += usage.completion_tokens

            output = response.choices[0].message.content.strip()
            if is_answer_acceptable(output):
                return output
            else:
                print(f"⚠️ Malformed output. Retrying... ({attempt + 1}/{max_retries})")
                print("🔻 GPT raw output (unacceptable):")
                print(output)
                time.sleep(delay)

        except openai.RateLimitError:
            print(f"⚠️ RateLimitError: sleeping {delay} seconds...")
            time.sleep(delay)
            delay *= 2

        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(delay)

    print("❌ Failed after max retries. Skipping row.")
    return False

# ------------------------- Main Execution -------------------------

if __name__ == "__main__":
    # Arguments
    input_path = sys.argv[1]
    text_field = sys.argv[2] if len(sys.argv) > 2 else "sentence"
    keyword_field = sys.argv[3] if len(sys.argv) > 3 else "keyword"
    model_name = "gpt-4o-mini"

    print(f"\n📥 Input file: {input_path}")
    print(f"🔎 Text field: '{text_field}'")
    print(f"🔑 Keyword field: '{keyword_field}'")

    # Paths
    instruction_path = "./prompts/instruction.txt"
    icl_path = "./prompts/icl.jsonl"

    # OpenAI Client
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Pricing setup
    price_map = {
        "gpt-4o": (0.0025, 0.0100),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-3.5-turbo": (0.0005, 0.0015)
    }
    if model_name not in price_map:
        raise ValueError(f"Unknown model: {model_name}")
    price_in, price_out = price_map[model_name]

    # Model information
    print(f"\n🔧 Using prompting model: {model_name}")
    print(f"   ├─ Input token price: ${price_in:.6f}")
    print(f"   └─ Output token price: ${price_out:.6f}")

    # Load ICL
    icl_messages = load_icl_messages(instruction_path, icl_path)

    print(f"📄 Instruction prompt: {instruction_path}")
    print(f"📄 ICL examples: {icl_path}")

    # Output setup
    _, filename = os.path.split(input_path)  # filename: knife.jsonl
    keyword = os.path.splitext(filename)[0]  # knife

    # Output path
    output_dir = os.path.join("scene", keyword)
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"{keyword}-{model_name}.jsonl")
    failed_file = os.path.join(output_dir, f"{keyword}-{model_name}-failed.jsonl")

    print(f"\n💾 Output file: {output_file}")
    print(f"💥 Failed cases file: {failed_file}")

    failed_count = 0

    # Main loop
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_file, 'a', encoding='utf-8') as outfile, \
         open(failed_file, 'w', encoding='utf-8') as failfile:

        for line in tqdm(infile.readlines()):
            row = json.loads(line)
            print("\n🔹 Input:", row[text_field])

            result = ask_gpt(client, row, text_field, keyword_field, icl_messages, gpt_model=model_name)

            row["gpt_output"] = result if result else None
            target_file = outfile if result and is_answer_acceptable(result) else failfile
            target_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            target_file.flush()

            if not result or not is_answer_acceptable(result):
                failed_count += 1

    # Cleanup
    if failed_count == 0:
        if os.path.exists(failed_file):
            os.remove(failed_file)
        print("\n✅ No failed cases. Cleaned up.")
    else:
        print(f"\n❌ {failed_count} failed case(s). See: {failed_file}")

    # Cost report
    estimate_cost_gpt(model_name, price_in, price_out)
