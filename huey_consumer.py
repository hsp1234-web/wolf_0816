# This is the main entry point for the Huey consumer process.
# You can run it from the command line like so:
# huey_consumer.py huey_consumer.huey --workers 2 --worker-type thread
#
# It imports the configured `huey` instance from our queue_config.
# The consumer will automatically discover any tasks registered with this
# instance by virtue of other modules being imported that use the @huey.task() decorator.

from src.core.queue_config import huey

# To make tasks discoverable, we need to import the modules where they are defined.
import workers.transcription_worker
import workers.logging_worker
import workers.hardware_monitor_worker

# The `huey` object itself is the primary export for the consumer.
