# Scene abstraction

Given a sentence and a target keyword, `src/scene.py` prompts GPT (gpt-4o-mini by
default) to extract a structured "scene abstraction": the events, entities, and
setting around the keyword, plus a profile of how the keyword itself behaves in
the scene. `src/utils.py` then turns that raw text back into structured data.

## Project layout

```
input/                    input files, e.g. input/<keyword>.jsonl
prompts/
  instruction.txt        the system instruction sent to the model
  icl.jsonl               in-context (few-shot) examples
src/
  scene.py                runs the model over an input file, row by row
  utils.py                parses gpt_output back into structured data
  browser.py              interactive terminal viewer for scene.py's output
scene/                    scene.py's output lands here
```

## Running scene.py

```bash
export OPENAI_API_KEY=...
python3 src/scene.py <input_file.jsonl> [<text_field>] [<keyword_field>]
```

- `text_field` defaults to `"sentence"`; for the sample data in `input/`, use
  `keyword_sentence` (that's the field holding the sentence text).
- `keyword_field` defaults to `"keyword"`.

Example, matching the sample data here:

```bash
python3 src/scene.py input/raccoon.jsonl keyword_sentence keyword
```

Output is written to `scene/<keyword>/<keyword>-<model>.jsonl`, where
`<keyword>` is the input file's basename (e.g. `input/raccoon.jsonl` ->
`scene/raccoon/`) — the input file's parent directory doesn't affect the
output path. Rows whose output fails validation are written to a sibling
`-failed.jsonl` file instead; if none fail, that file is removed.

## Browsing scene outputs interactively

`src/browser.py` is a terminal viewer for scanning through a keyword's scene
outputs one row at a time, without writing any parsing code:

```bash
python3 src/browser.py <keyword>
```

It looks for that keyword's (non-`-failed`) output file anywhere under
`./scene/` (`scene/<keyword>/<keyword>-*.jsonl`) and uses the first match.
Note the `<keyword>` argument must match the **output file's** name (the
input file's basename, per `scene.py`'s naming), not necessarily every row's
`keyword` field value — e.g. for `input/raccoon.jsonl` -> `scene/raccoon/`,
run `python3 src/browser.py raccoon`.

Once running:

| Key         | Action                                   |
|-------------|-------------------------------------------|
| Enter / `n` | next row                                  |
| `p`         | previous row                              |
| `/text`     | jump to the next row where `text` (regex) matches the sentence or `gpt_output`, highlighted |
| `q`         | quit                                      |

Each row shows the sentence, the full `gpt_output` text, and whatever
identifying metadata the row happens to have (`id`, `scene label`, `scene-id`,
`text-id`, `cluster`, `article_id`, ...) — fields your input schema doesn't
have are simply omitted, so this works across differently-shaped input files.

## Parsing scene outputs

`src/scene.py` writes one JSON object per line to `scene/<keyword>/<keyword>-<model>.jsonl`.
Each row is the original input row plus a `gpt_output` field: raw text from the model,
formatted as a bullet list with two sections, **Scene Overview** and **Scene Profile**
(see `prompts/instruction.txt`):

```
**Scene Overview:**
- **Events:**
  - PersonX locks herself in PlaceX
  - PersonX sobs
- **Entities:**
  - PersonX (she)
    - Role: Agent (Locking_in)
    - Property: Vulnerable (Her unpreparedness indicates a lack of readiness.)
    - Emotion: Distress (Implied by her sobbing.)
  - PlaceX (the bathroom)
    - Role: Location (Being_located)
    - Property: Private space (It provides a sense of seclusion.)
- **Setting:**
  - Place: bathroom (Specificity: high)
  - Time: unspecified (Specificity: low)
  - Atmosphere: tense and emotionally charged (...)

**Scene Profile:**
- Keyword: bathroom (Label: PlaceX)
- Engaged Events:
  - PersonX locks herself in them
- Generalizable Properties:
  - It serves as a refuge during emotional turmoil
- Evoked emotions:
  - Distress (The setting is associated with moments of personal crisis.)
```

`src/utils.py` has three functions for turning this text into structured data:
`load_jsonl`, `parse_gpt_output`, and `split_target_context_entities`.

### 1. Load the output file

```python
from utils import load_jsonl

rows = load_jsonl("scene/raccoon/raccoon-gpt-4o-mini.jsonl")
row = rows[0]
row["gpt_output"]   # the raw bullet-list text shown above
```

### 2. Parse `gpt_output` into a dict

```python
from utils import parse_gpt_output

parsed = parse_gpt_output(row["gpt_output"])
```

`parsed` always has these keys (each is `None`/empty if that field wasn't present
in the model's output, or if `gpt_output` itself wasn't a string, e.g. a failed row):

| Key                        | Type                          | Comes from            |
|-----------------------------|-------------------------------|------------------------|
| `events`                    | `list[str]` or `None`         | Scene Overview > Events |
| `entities`                  | `dict[label -> entity]` or `None` | Scene Overview > Entities |
| `setting_place`              | `{"place", "specificity"}` or `None` | Scene Overview > Setting |
| `setting_time`                | `{"time", "specificity"}` or `None`  | Scene Overview > Setting |
| `setting_atmosphere`          | `{"atmosphere", "explanation"}` or `None` | Scene Overview > Setting |
| `keyword_label`              | `str` or `None`                | Scene Profile > Keyword |
| `engaged_events`             | `list[str]` or `None`          | Scene Profile > Engaged Events |
| `generalizable_properties`   | `list[str]` or `None`          | Scene Profile > Generalizable Properties |
| `evoked_emotions`            | `list[{"emotion","explanation"}]` or `None` | Scene Profile > Evoked emotions |

Each entity in `entities` is keyed by its label (`"PersonX"`, `"PlaceX"`, ...) and has:

```python
{
    "mention": "she",              # the surface mention, e.g. "PersonX (she)"
    "roles": [{"role": "Agent", "frame": "Locking_in"}, ...],
    "properties": [{"property": "Vulnerable", "explanation": "..."}, ...],
    "emotions": [{"emotion": "Distress", "explanation": "..."}, ...],
}
```

### Fetching individual components

```python
parsed["events"]                      # list of COMET-ATOMIC-style event strings
parsed["entities"]["PersonX"]["roles"]        # this entity's (role, frame) pairs
parsed["entities"]["PersonX"]["properties"]   # this entity's properties + explanations
parsed["entities"]["PersonX"]["emotions"]     # this entity's emotions + explanations

parsed["setting_place"]["place"]              # e.g. "bathroom"
parsed["setting_place"]["specificity"]        # e.g. "high"
parsed["setting_time"]
parsed["setting_atmosphere"]

parsed["keyword_label"]               # which entity label realizes the keyword, e.g. "PlaceX"
parsed["engaged_events"]
parsed["generalizable_properties"]
parsed["evoked_emotions"]
```

### 3. Target entity vs. context entities

`parsed["entities"]` mixes together every entity in the scene. Whether an entity
*is* the target keyword or just part of the surrounding context matters for most
downstream analysis, so use `split_target_context_entities`:

```python
from utils import split_target_context_entities

target_entities, context_entities = split_target_context_entities(parsed)
```

- **Target entity**: the entity whose label matches `parsed["keyword_label"]`
  (Scene Profile > Keyword > `Label: ...`) — i.e. the entity that *is* the target
  keyword in this scene. `target_entities` is a `{label: entity}` dict with at
  most one entry.
- **Context entities**: every other entity in the scene (`{label: entity}`,
  possibly empty).
- **When the keyword isn't a noun/entity** (e.g. the keyword is a verb or
  adjective and the model never assigns it an entity label), `keyword_label` is
  `None` or doesn't match any entity. In that case `target_entities` is `{}`
  (empty) and `context_entities` contains every entity in the scene — there is
  no target entity to report.

```python
if target_entities:
    label, target = next(iter(target_entities.items()))
    print(f"Target entity ({label}): roles={target['roles']}")
else:
    print("Keyword is not realized as an entity in this scene.")

for label, ctx in context_entities.items():
    print(f"Context entity {label}: {ctx['mention']}")
```

### 4. Putting it together

```python
from utils import load_jsonl, parse_gpt_output, split_target_context_entities

for row in load_jsonl("scene/raccoon/raccoon-gpt-4o-mini.jsonl"):
    parsed = parse_gpt_output(row["gpt_output"])
    target, context = split_target_context_entities(parsed)

    print(row.get("id", "(no id)"), "-", row["keyword_sentence"])
    print("  events:", parsed["events"])
    print("  setting:", parsed["setting_place"], parsed["setting_time"], parsed["setting_atmosphere"])
    print("  target entity:", target)
    print("  context entities:", list(context.keys()))
    print("  scene profile:", parsed["engaged_events"], parsed["generalizable_properties"], parsed["evoked_emotions"])
```
