"""
arc_1_recog_gen.py
------------------

Harness for the Recognition vs. Generation study on ARC-AGI-1.

Provides:
- call_claude: thin wrapper around the Anthropic Messages API with token logging
- build_prompt: format an ARC task as a generation prompt
- build_recognition_prompt: format an ARC task as a 2AFC recognition prompt
- parse_response: extract a 2D grid from a model's generation response
- parse_recognition_response: extract X or Y from a recognition response
- score_attempt: score a model answer against ground truth (binary + cell Hamming)
- perturb_grid: generate a perturbation distractor from a ground-truth grid

Parser logic (backscan_json_parser, extract_from_boxed) is adapted from
arcprize/arc-agi-benchmarking (src/arc_agi_benchmarking/utils/parsing.py).
"""

import json
import os
import random
import re
from datetime import datetime, timezone
from typing import Callable, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv


# Load API key from .env into environment variables
load_dotenv()

# Create the client (auto-reads ANTHROPIC_API_KEY from environment)
client = Anthropic()


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are participating in a puzzle solving competition. You are an expert at solving puzzles.

Below is a list of input and output pairs with a pattern. Your goal is to identify the pattern or transformation in the training examples that maps the input to the output, then apply that pattern to the test input to give a final output.

Respond in the format of the training output examples

--Training Examples--

{training_examples}

--End of Training Examples--

--Test Input--

{test_input}

--End of Test Input--

Your response:"""


RECOGNITION_PROMPT_TEMPLATE = """You are participating in a puzzle solving competition. You are an expert at solving puzzles.

Below is a list of input and output pairs with a pattern. Your goal is to identify the pattern or transformation in the training examples that maps the input to the output, then determine which of two candidate answers correctly applies that pattern to the test input. Exactly one of the candidate answers is correct.

--Training Examples--

{training_examples}

--End of Training Examples--

--Test Input--

{test_input}

--End of Test Input--

Which one of the following two candidate answers is the correct output for the test input?

--Candidate X--

{candidate_x}

--End of Candidate X--

--Candidate Y--

{candidate_y}

--End of Candidate Y--

After you have decided your answer, indicate it by ending your response with one of the following:
<answer>X</answer>
<answer>Y</answer>"""


# ---------------------------------------------------------------------------
# API harness
# ---------------------------------------------------------------------------

def call_claude(prompt: str, model: str = "claude-sonnet-4-6", thinking_budget: int = 8000) -> dict:
    """
    Send a prompt to Claude and return the response.

    If thinking_budget is 0 (or less than 1024), thinking is disabled.
    Otherwise, extended thinking is enabled with the given budget.

    Returns a dict with text, thinking, input_tokens, output_tokens, model, timestamp.
    """
    request_kwargs = {
        "model": model,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}],
    }

    if thinking_budget and thinking_budget >= 1024:
        request_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    response = client.messages.create(**request_kwargs)

    text_blocks = [b.text for b in response.content if b.type == "text"]
    thinking_blocks = [b.thinking for b in response.content if b.type == "thinking"]

    return {
        "text": "\n".join(text_blocks),
        "thinking": "\n".join(thinking_blocks),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": response.model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_prompt(task: dict) -> str:
    """
    Build a generation prompt from an ARC task dict (with 'train' and 'test' keys).
    """
    training_examples = ""
    for i, pair in enumerate(task["train"]):
        training_examples += f"--Example {i}-- \n\n INPUT: \n\n"
        training_examples += json.dumps(pair["input"]) + "\n\n"
        training_examples += "OUTPUT: \n\n"
        training_examples += json.dumps(pair["output"]) + "\n\n"

    test_input = task["test"][0]["input"]
    test_input_str = json.dumps(test_input)

    return PROMPT_TEMPLATE.format(
        training_examples=training_examples,
        test_input=test_input_str,
    )


def build_recognition_prompt(task: dict, candidate_x: list, candidate_y: list) -> str:
    """
    Build a 2AFC recognition prompt with two labeled candidate answers.

    task: ARC task dict
    candidate_x: 2D list to display as Candidate X
    candidate_y: 2D list to display as Candidate Y
    """
    training_examples = ""
    for i, pair in enumerate(task["train"]):
        training_examples += f"--Example {i}-- \n\n INPUT: \n\n"
        training_examples += json.dumps(pair["input"]) + "\n\n"
        training_examples += "OUTPUT: \n\n"
        training_examples += json.dumps(pair["output"]) + "\n\n"

    test_input = task["test"][0]["input"]
    test_input_str = json.dumps(test_input)
    candidate_x_str = json.dumps(candidate_x)
    candidate_y_str = json.dumps(candidate_y)

    return RECOGNITION_PROMPT_TEMPLATE.format(
        training_examples=training_examples,
        test_input=test_input_str,
        candidate_x=candidate_x_str,
        candidate_y=candidate_y_str,
    )


# ---------------------------------------------------------------------------
# Response parsing
# Parser logic adapted from arcprize/arc-agi-benchmarking
# (src/arc_agi_benchmarking/utils/parsing.py)
# ---------------------------------------------------------------------------

def backscan_json_parser(log_str: str) -> Optional[List[List[int]]]:
    """
    Extract the last valid JSON list-of-lists substring from the given string
    by scanning backwards from the end.

    Returns the parsed list of lists if found and valid, otherwise None.
    """
    last_bracket_idx = -1
    closing_bracket = None
    for i in range(len(log_str) - 1, -1, -1):
        char = log_str[i]
        if char in (']', '}'):
            last_bracket_idx = i
            closing_bracket = char
            break

    if last_bracket_idx == -1:
        return None

    opening_bracket = '[' if closing_bracket == ']' else '{'

    bracket_counter = 1  # account for the closing bracket we just found
    start_idx = -1

    for i in range(last_bracket_idx - 1, -1, -1):
        char = log_str[i]
        if char == closing_bracket:
            bracket_counter += 1
        elif char == opening_bracket:
            bracket_counter -= 1
            if bracket_counter == 0:
                start_idx = i
                break

    if start_idx == -1:
        return None

    json_candidate = log_str[start_idx:last_bracket_idx + 1]

    try:
        parsed_json = json.loads(json_candidate)
        if (
            isinstance(parsed_json, list)
            and parsed_json
            and all(isinstance(row, list) for row in parsed_json)
        ):
            return parsed_json
        return None
    except json.JSONDecodeError:
        return None


def extract_from_boxed(log_str: str) -> Optional[List[List[int]]]:
    """
    Extract a list-of-lists from a LaTeX-style \\boxed{} command if present.
    """
    match = re.search(r"\\boxed\{(.*?)\}", log_str, re.DOTALL)
    if match:
        content = match.group(1).strip()
        try:
            parsed_json = json.loads(content)
            if isinstance(parsed_json, list) and all(isinstance(i, list) for i in parsed_json):
                return parsed_json
        except json.JSONDecodeError:
            pass
    return None


def parse_response(response: str) -> Optional[List[List[int]]]:
    """
    Try multiple parsing strategies on a model response and return the parsed
    grid, or None if no strategy succeeds.

    Strategies (tried in order):
    1. extract_from_boxed: LaTeX \\boxed{} wrapper
    2. backscan_json_parser: scan backwards for JSON brackets
    """
    for parser in [extract_from_boxed, backscan_json_parser]:
        try:
            result = parser(response)
            if (
                result is not None
                and isinstance(result, list)
                and all(isinstance(row, list) for row in result)
            ):
                return result
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def parse_recognition_response(response_text: str) -> Optional[str]:
    """
    Find <answer>X</answer> or <answer>Y</answer> in a recognition response.

    Returns 'X', 'Y', or None (when no tag is found, or multiple distinct
    answers appear).
    """
    matches = re.findall(r'<answer>([XY])</answer>', response_text)
    if not matches:
        return None
    distinct = set(matches)
    if len(distinct) == 1:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_attempt(model_answer, ground_truth) -> dict:
    """
    Score a single attempt against ground truth.

    model_answer: 2D list, or None if parsing failed
    ground_truth: 2D list (the correct answer)

    Returns a dict with 'status' and 'cell_hamming' keys. Status is one of:
    'unparseable', 'correct', or 'incorrect'. cell_hamming is a float in
    [0, 1] or None when not well-defined.
    """
    if model_answer is None:
        return {"status": "unparseable", "cell_hamming": None}

    if model_answer == ground_truth:
        return {"status": "correct", "cell_hamming": 1.0}

    rows_match = len(model_answer) == len(ground_truth)
    cols_match = rows_match and all(
        len(mr) == len(gr)
        for mr, gr in zip(model_answer, ground_truth)
    )

    if not (rows_match and cols_match):
        # Different shape: Hamming similarity is not well-defined
        return {"status": "incorrect", "cell_hamming": None}

    matches = sum(
        1
        for row1, row2 in zip(model_answer, ground_truth)
        for cell1, cell2 in zip(row1, row2)
        if cell1 == cell2
    )
    total = sum(len(row) for row in ground_truth)

    return {"status": "incorrect", "cell_hamming": matches / total}


# ---------------------------------------------------------------------------
# Distractor generation
# ---------------------------------------------------------------------------

def perturb_grid(grid, fraction_to_flip: float = 0.05, seed: Optional[int] = None) -> list:
    """
    Generate a perturbation distractor by flipping ~fraction_to_flip of cells
    in the grid to other values from the grid's existing color palette.

    Returns a perturbed copy of the grid.
    """
    if seed is not None:
        random.seed(seed)

    perturbed = [row[:] for row in grid]
    palette = set(v for row in grid for v in row)

    rows = len(grid)
    cols = len(grid[0])
    total_cells = rows * cols

    n_flips = max(1, round(fraction_to_flip * total_cells))
    all_positions = [(r, c) for r in range(rows) for c in range(cols)]
    flip_positions = random.sample(all_positions, n_flips)

    for r, c in flip_positions:
        original_val = grid[r][c]
        candidates = [v for v in palette if v != original_val]
        if not candidates:
            candidates = [v for v in range(10) if v != original_val]
        perturbed[r][c] = random.choice(candidates)

    return perturbed
