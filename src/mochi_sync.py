from functools import lru_cache
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
import string
import tomllib
from typing import Generator
import uuid
import zipfile
from google import genai
from google.genai import types, errors
from pydantic import BaseModel, field_validator
from transit.transit_types import Keyword
from transit.writer import TaggedValue, Writer
import io


class Config(BaseModel):
    api_key: str
    input_directory: str
    output_file: str
    model: str
    card_template: str
    first_language: str
    second_language: str
    second_language_level: str
    retry_attempts: int
    retry_delay: int
    android_device_id: str
    android_path: str

    @field_validator("input_directory", "output_file", mode="before")
    @classmethod
    def resolve_path(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            return str(Path(__file__).parent.parent / p)
        return v
    
    @field_validator("retry_attempts", "retry_delay")
    @classmethod
    def validate_non_zero(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Value must be at least 1")
        return v
        


class Flashcard(BaseModel):
    word: str
    translation: str
    transcription: str
    example: str


class Deck(BaseModel):
    name: str
    cards: list[Flashcard]


@lru_cache()
def platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"

    if sys.platform == "darwin":
        return "darwin"

    if sys.platform in {"win32", "cygwin", "msys"}:
        return "windows"


@lru_cache()
def adb_path() -> str:
    if platform() == "windows":
        adb_executable = "adb.exe"
    else:
        adb_executable = "adb"

    adb_path = Path(__file__).parent.parent / "platform_tools" / platform() / adb_executable

    return adb_path.as_posix()


def adb(*args: tuple[str, ...]) -> None:
    subprocess.run([adb_path(), *args], check=True)


def load_config() -> Config:
    config_path = Path(__file__).parent.parent / "config.toml"
    with config_path.open("rb") as f:
        return Config(**tomllib.load(f))


def save_deck(deck: Deck, config: Config) -> None:
    print("Saving deck...")

    deck_id = Keyword(uuid.uuid4().hex)

    cards_data = [
        {
            Keyword("deck-id"): deck_id,
            Keyword("content"): string.Template(config.card_template).substitute(**card.model_dump())
        }
        for card in deck.cards
    ]

    decks_data = [{
        Keyword("id"): deck_id,
        Keyword("name"): deck.name,
        Keyword("cards"): TaggedValue("list", cards_data)
    }]

    mochi_data = {
        Keyword("version"): 2,
        Keyword("decks"): decks_data,
    }

    io_obj = io.StringIO()
    writer = Writer(io_obj, "json_verbose")
    writer.write(mochi_data)
    transit_json = io_obj.getvalue()

    with zipfile.ZipFile(config.output_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", transit_json)

    print(f"Deck saved to {config.output_file}")


def make_prompt(config: Config) -> str:
    prompt_file = Path(__file__).parent / "prompt.md"
    with prompt_file.open("r", encoding="utf-8") as f:
        prompt_template = f.read()
    return string.Template(prompt_template).substitute(**config.model_dump())


@contextmanager
def managed_uploads(client: genai.Client, directory: str) -> Generator[list[genai.types.File], None, None]:
    uploaded_files: list[genai.types.File] = []
    try:
        for file in Path(directory).glob("*"):
            if file.is_file():
                print(f"Uploading file {file}...")
                uploaded_files.append(client.files.upload(file=file))
        yield uploaded_files
    finally:
        print("Deleting uploaded files...")
        for f in uploaded_files:
            if f.name is not None:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass


def make_deck(client: genai.Client, config: Config) -> Deck:
    with managed_uploads(client, config.input_directory) as uploaded_files:
        if not uploaded_files:
            raise ValueError("No input files found in the input directory")

        contents = [*uploaded_files, make_prompt(config)]
        content_config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Deck)
        
        last_exception = None
        for attempt in range(config.retry_attempts):
            try:
                print(f"Attempting to generate content ({attempt + 1}/{config.retry_attempts})...")
                response = client.models.generate_content(model=config.model, contents=contents, config=content_config)
                if response.text is None:
                    raise ValueError("Received empty response from the model")

                if not isinstance(response.parsed, Deck):
                    raise ValueError("Parsed response is not of type Deck")
                    
                return response.parsed
            except errors.APIError as e:
                if e.code in (429, 500, 502, 503):
                    last_exception = e
                    if attempt < config.retry_attempts - 1:
                        print(f"Server overloaded (status {e.code}). Retrying in {config.retry_delay} seconds...")
                        time.sleep(config.retry_delay)
                    else:
                        print(f"Server overloaded (status {e.code}). No more retry attempts left")
                else:
                    raise
                    
        raise RuntimeError(f"Failed to generate content after {config.retry_attempts} attempts.") from last_exception


def push_to_device(config: Config) -> None:
    if not config.android_path:
        print("Android path is not set. Skipping push to device.")
        return

    device_id_args = []
    if config.android_device_id:
        device_id_args = ["-s", config.android_device_id]

    print(f"Pushing deck to Android device at {config.android_path}...")
    adb(*device_id_args, "push", config.output_file, config.android_path)
    print("Deck pushed successfully")


def main() -> None:
    config = load_config()
    client = genai.Client(api_key=config.api_key)
    deck = make_deck(client, config)
    save_deck(deck, config)
    push_to_device(config)

    print("All done!")


if __name__ == "__main__":
    main()