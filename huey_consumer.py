# This is the main entry point for the Huey consumer process.
# It defines the `huey` instance, making it discoverable by the huey runner.

from huey import SqliteHuey
from pathlib import Path

# Define the root directory relative to this file's location
ROOT_DIR = Path(__file__).resolve().parent

# Define the path for the queue database
QUEUE_DB_PATH = ROOT_DIR / "queue.db"

# Create the shared Huey instance.
# This is the object that the `huey_consumer.py` executable looks for.
huey = SqliteHuey(filename=str(QUEUE_DB_PATH))


# To make tasks discoverable, we need to import the modules where they are defined.
import workers.transcription_worker
import workers.logging_worker
