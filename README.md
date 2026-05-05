# Recognition vs. Generation on ARC-AGI-1

A small single-model study applying assessment-development concepts (partial credit, recognition vs. generation, controlled distractors) to evaluation of Claude Sonnet 4.6 on the ARC-AGI-1 public evaluation set.

**Full writeup:** [WRITEUP.md](WRITEUP.md)

## Summary of findings

- **Cell-level partial credit reveals near-misses that binary scoring obscures.** Of 32 wrong generation attempts, the median missed by just 8 cells. The closest near-miss was a single cell wrong out of 462. ARC's binary scoring conflates these near-misses with attempts that get the rule entirely wrong.

- **A small recognition-generation gap is present.** On 2 of 30 tasks, the model failed to generate the correct answer in any of three attempts but recognized it correctly in both recognition trials. One of those tasks involved a token-budget exhaustion where the model produced no output at all but still discriminated correctly when shown candidates.

- **Distractor type matters substantially.** Recognition accuracy was 100% (26/26) on perturbation distractors but only 62% (21/34) on distractors drawn from the model's own wrong attempts, despite comparable Hamming similarity to ground truth. The model's own wrongs are uniquely confusable to it.

## Repository contents

- [`WRITEUP.md`](WRITEUP.md) — full study writeup with charts and findings
- [`arc_1_recog_gen.py`](arc_1_recog_gen.py) — harness module: API client, prompt builders, parsers, scoring
- [`notebook.ipynb`](notebook.ipynb) — Jupyter notebook with the full study run, end to end
- [`data/`](data/) — sampled task IDs, distractors, generation results, recognition results
- [`charts/`](charts/) — chart images referenced in the writeup

## Reproduction

```bash
# Clone this repo and ARC-AGI as siblings
git clone https://github.com/jsakovich/arc-recognition-generation.git
git clone https://github.com/fchollet/ARC-AGI.git

cd arc-recognition-generation

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Add Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Run the notebook end to end
jupyter lab notebook.ipynb
```

API cost for the full study is approximately $15.

## License

MIT. Code and data are released for reuse and extension. See [`LICENSE`](LICENSE).

## About

This is an exploratory study examining whether methodologies and mindset from high-stakes assessment development can be applied to AI model evaluation. The study brings a few concepts from assessments and psychometrics (partial credit, controlled distractors, item-level analysis) into a frontier-model evaluation context where they are underused. Substantially more work along these lines is possible.

Reach out at sakovichj@gmail.com or via GitHub issues if you have questions or want to extend the work.
