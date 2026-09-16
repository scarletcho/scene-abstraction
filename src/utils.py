# utils.py
#
# Parsing utilities for scene.py's gpt_output field:
# "**Scene Overview:**" (Events / Entities / Setting) + "**Scene Profile:**".

import json
import re


def load_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_gpt_output(text):

    if not isinstance(text, str):
        return {
            "events": None,
            "entities": None,
            "setting_place": None,
            "setting_time": None,
            "setting_atmosphere": None,
            "keyword_label": None,
            "engaged_events": None,
            "generalizable_properties": None,
            "evoked_emotions": None,
        }

    output = {
        "events": [],
        "entities": {},
        "setting_place": None,
        "setting_time": None,
        "setting_atmosphere": None,
        "keyword_label": None,
        "engaged_events": [],
        "generalizable_properties": [],
        "evoked_emotions": [],
    }

    current_section = None
    sub_section = None
    current_entity = None
    entity_buffer = {}

    lines = text.strip().split("\n")

    def header_of(raw_line: str) -> str:
        # Section headers may appear flat ("**Events:**") or nested one level
        # under "**Scene Overview:**" as a bullet ("- **Events:**").
        s = raw_line.strip()
        return s[2:].strip() if s.startswith("- **") else s

    for i, line in enumerate(lines):
        striped = line.strip()
        header = header_of(line)

        # === Section headers ===
        if header.startswith("**Scene Overview:**"):
            continue
        elif header.startswith("**Events:**"):
            current_section = "events"
            continue
        elif header.startswith("**Entities:**"):
            current_section = "entities"
            continue
        elif header.startswith("**Setting:**"):
            current_section = "setting"
            continue
        elif header.startswith("**Scene Profile:**"):
            current_section = "keyword_analysis"
            sub_section = None
            continue

        # === Main content ===
        if current_section == "events":
            if striped.startswith("- "):
                output["events"].append(striped[2:].strip())

        elif current_section == "entities":
            if striped.startswith("- ") and not striped.startswith(("- Role:", "- Property:", "- Emotion:")):
                if current_entity:
                    output["entities"][current_entity] = entity_buffer
                match = re.match(r"- ([^()]+) \(([^()]+)\)", striped)
                if match:
                    label = match.group(1).strip()
                    mention = match.group(2).strip()
                    current_entity = label
                    entity_buffer = {
                        "mention": mention,
                        "roles": [],
                        "properties": [],
                        "emotions": []
                    }
            elif striped.startswith("- Role:"):
                m = re.match(r"- Role: (.+?) \((.+?)\)", striped)
                if m and current_entity:
                    entity_buffer["roles"].append({
                        "role": m.group(1).strip(),
                        "frame": m.group(2).strip()
                    })
            elif striped.startswith("- Property:"):
                if current_entity:
                    prop_line = striped[len("- Property:"):].strip()
                    m = re.match(r"(.+?) \((.+?)\)", prop_line)
                    if m:
                        entity_buffer["properties"].append({
                            "property": m.group(1).strip(),
                            "explanation": m.group(2).strip()
                        })
                    else:
                        entity_buffer["properties"].append({
                            "property": prop_line,
                            "explanation": ""
                        })
            elif striped.startswith("- Emotion:"):
                if current_entity:
                    emo_line = striped[len("- Emotion:"):].strip()
                    m = re.match(r"(.+?) \((.+?)\)", emo_line)
                    if m:
                        entity_buffer["emotions"].append({
                            "emotion": m.group(1).strip(),
                            "explanation": m.group(2).strip()
                        })
                    else:
                        entity_buffer["emotions"].append({
                            "emotion": emo_line,
                            "explanation": ""
                        })

            if i == len(lines) - 1 or header_of(lines[i+1]).startswith("**"):
                if current_entity:
                    output["entities"][current_entity] = entity_buffer
                    current_entity = None
                    entity_buffer = {}

        elif current_section == "setting":
            if striped.startswith("- Place:"):
                line = striped[len("- Place:"):].strip()
                m = re.match(r"(.+?) \(Specificity: (.+?)\)", line)
                if m:
                    output["setting_place"] = {
                        "place": m.group(1).strip(),
                        "specificity": m.group(2).strip()
                    }
                else:
                    output["setting_place"] = {
                        "place": line,
                        "specificity": None
                    }
            elif striped.startswith("- Time:"):
                line = striped[len("- Time:"):].strip()
                m = re.match(r"(.+?) \(Specificity: (.+?)\)", line)
                if m:
                    output["setting_time"] = {
                        "time": m.group(1).strip(),
                        "specificity": m.group(2).strip()
                    }
                else:
                    output["setting_time"] = {
                        "time": line,
                        "specificity": None
                    }
            elif striped.startswith("- Atmosphere:"):
                atmo_line = striped[len("- Atmosphere:"):].strip()
                m = re.match(r"(.+?) \((.+?)\)", atmo_line)
                if m:
                    output["setting_atmosphere"] = {
                        "atmosphere": m.group(1).strip(),
                        "explanation": m.group(2).strip()
                    }
                else:
                    output["setting_atmosphere"] = {
                        "atmosphere": atmo_line,
                        "explanation": ""
                    }

        elif current_section == "keyword_analysis":
            if striped.startswith("- Keyword:"):
                m = re.match(r"- Keyword: .+?\(Label: (.+?)\)", striped)
                if m:
                    output["keyword_label"] = m.group(1).strip()
                sub_section = None
            elif striped.startswith("- Engaged Events:"):
                sub_section = "engaged"
            elif striped.startswith("- Generalizable Properties:"):
                sub_section = "properties"
            elif striped.startswith("- Evoked emotions:"):
                sub_section = "emotions"
            elif striped.startswith("- "):  # Bullet lines
                content = striped[2:].strip()
                if sub_section == "engaged":
                    output["engaged_events"].append(content)
                elif sub_section == "properties":
                    output["generalizable_properties"].append(content)
                elif sub_section == "emotions":
                    m = re.match(r"(.+?) \((.+?)\)", content)
                    if m:
                        output["evoked_emotions"].append({
                            "emotion": m.group(1).strip(),
                            "explanation": m.group(2).strip()
                        })
                    else:
                        output["evoked_emotions"].append({
                            "emotion": content,
                            "explanation": ""
                        })

    # Clean-up None fields
    for key in ["events", "engaged_events", "generalizable_properties", "evoked_emotions"]:
        if not output[key]:
            output[key] = None
    if not output["entities"]:
        output["entities"] = None

    return output


def split_target_context_entities(parsed: dict):
    """
    Split parsed["entities"] into the target entity (the one realizing the
    keyword, per parsed["keyword_label"]) and the context entities (everyone
    else in the scene).

    Returns (target_entities, context_entities), each a dict of
    {entity_label: entity_dict}. target_entities is empty when the keyword
    isn't realized as an entity (e.g. the keyword isn't a noun), in which
    case every entity in the scene is treated as a context entity.
    """
    entities = parsed.get("entities") or {}
    keyword_label = parsed.get("keyword_label")

    if keyword_label and keyword_label in entities:
        target_entities = {keyword_label: entities[keyword_label]}
        context_entities = {k: v for k, v in entities.items() if k != keyword_label}
    else:
        target_entities = {}
        context_entities = dict(entities)

    return target_entities, context_entities
