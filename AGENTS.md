# AI Agent Development Guidelines

This document outlines the specific requirements and constraints for developing and testing this project. All AI agents working on this repository must adhere to these guidelines.

## 1. Development Goal

The primary goal is to restore all backend API endpoints and integrate them correctly with the existing Vue.js frontend. The main references for this task are `api_server_old.py` for backend logic and the current Vue application's structure.

## 2. Testing and Dependency Strategy

- **Mocking is Mandatory**: All tests must be conducted using a mock framework with fake data. The previous mock test files are lost and must be rewritten.
- **No Large Dependencies**: The system environment has severe resource limitations (disk space, memory). Therefore, the installation or use of any large dependencies is strictly forbidden. The agent must identify and simulate the functionality of these packages.
- **Specific Packages to Mock**: Based on `requirements-worker.txt`, the following packages must be mocked and should **not** be installed:
  - `torch`
  - `faster-whisper`
  - `google-generativeai`
  - `yt-dlp`
  - `pydub`
  - `WeasyPrint`

## 3. `localtest` Execution Script

A new script named `localtest` must be created by referencing the existing `local Run` script. This script will be the standard way to run the application for testing purposes.

### `localtest` Requirements:

- **Functionality**: The script must handle server startup and the execution of all lightweight tests.
- **Timeout Mechanism**: The server's shutdown process is unstable. To prevent zombie processes from crashing the toolchain, the `localtest` script **must** implement a **100-second timeout**. If the process is still running after 100 seconds, it must be forcefully terminated.

## 4. Codebase Context & History

- **Problem Origin**: The current task originated from a migration from a legacy, single-file frontend (`src/static/mp3.html`) to a modern Vue.js application (`vue-app/`).
- **Core Issue**: The main `src/api/api_server.py` was found to be an incomplete, stripped-down version, which was the root cause of the reported "missing features".
- **Resolution**: The primary fix was to merge the full-featured logic from a reference file (`api_server_old.py`) back into `src/api/api_server.py`, while carefully preserving the new logic required to serve the built Vue.js application.

## 5. Communication

All code comments, commit messages, and user-facing output must be in Traditional Chinese.
