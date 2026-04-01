# Mochi Sync

Mochi Sync is a tool that analyzes study materials (such as texts, vocab lists, and exercises) and automatically generates flashcard decks for the [Mochi](https://mochi.cards/) app using the Gemini API.

It reads input files, identifies vocabulary items, and creates comprehensive flashcards including the target word, its translation, its IPA transcription, and a natural example sentence at your desired language proficiency level. It then outputs a `.mochi` deck ready for import.

## Prerequisites

- [UV](https://docs.astral.sh/uv/getting-started/installation/)
- [A Google Gemini API key](https://ai.google.dev/gemini-api/docs/api-key)

## Setup & Configuration

Open `config.toml` and configure your settings:
   - Provide your `api_key`.
   - Set the `first_language` (your native language or the target translation language).
   - Set the `second_language` (the language you are learning).
   - Adjust `second_language_level` to set the complexity of the example sentences.

Optionally, you can fine-tune other settings if needed:
   - `input_directory` - directory to read study materials from
   - `output_file` - path to the generated `.mochi` deck
   - `model` - Gemini model to use
   - `card_template` - template for card content; supports placeholders `${word}`, `${translation}`, `${transcription}`, `${example}`
   - `retry_attempts` - number of retries on API failure
   - `retry_delay` - delay in seconds between retries

LLM prompt is located in `src/prompt.md`. You can modify it to better suit your needs or to include additional instructions for the Gemini API. Config values can be referenced in the prompt using `${variable_name}` syntax, allowing for dynamic content generation based on your configuration.

## Usage

Place your study materials in the `input_data/` directory, and run the main script:

```bash
./mochi_sync.sh
```

The script will process your documents, use the prompt in `src/prompt.md` to extract terms, and create a `deck.mochi` file in the root directory. You can then import this file directly into the Mochi app.

