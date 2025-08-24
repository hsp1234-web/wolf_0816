# This module's sole purpose is to import all the task-defining modules
# so that the tasks are registered with the huey instance.

import workers.transcription_worker
import workers.logging_worker
