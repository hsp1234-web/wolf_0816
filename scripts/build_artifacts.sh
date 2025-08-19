#!/bin/bash
set -e

# --- Configuration ---
# Get the script's directory and project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
ARTIFACTS_DIR="$PROJECT_ROOT/artifacts"
BACKEND_DEPS_ZIP="$ARTIFACTS_DIR/backend-deps.zip"
FRONTEND_DIST_ZIP="$ARTIFACTS_DIR/frontend-dist.zip"
TEMP_BUILD_DIR="$PROJECT_ROOT/temp_build"

echo "--- Pre-baking Artifacts ---"
echo "Project Root: $PROJECT_ROOT"
echo "Artifacts will be stored in: $ARTIFACTS_DIR"

# --- Cleanup and Setup ---
echo "Cleaning up old artifacts and temporary directories..."
rm -rf "$ARTIFACTS_DIR"/*
rm -rf "$TEMP_BUILD_DIR"
mkdir -p "$TEMP_BUILD_DIR/backend_deps"
mkdir -p "$ARTIFACTS_DIR"

# --- Backend Dependencies ---
echo "Step 1/2: Packaging backend dependencies..."
# We will install dependencies into a specific target directory to package them.
pip install --target="$TEMP_BUILD_DIR/backend_deps" -r "$PROJECT_ROOT/requirements-server.txt"

echo "Compressing backend dependencies..."
(cd "$TEMP_BUILD_DIR/backend_deps" && zip -r "$BACKEND_DEPS_ZIP" .)

echo "✅ Backend dependencies packaged successfully."

# --- Frontend Build ---
echo "Step 2/2: Building frontend application..."
FRONTEND_DIR="$PROJECT_ROOT/vue-app"
if [ -d "$FRONTEND_DIR" ]; then
  cd "$FRONTEND_DIR"
  echo "Installing frontend dependencies in $FRONTEND_DIR..."
  npm install
  echo "Building frontend..."
  npm run build

  echo "Compressing frontend build artifacts..."
  (cd "$FRONTEND_DIR/dist" && zip -r "$FRONTEND_DIST_ZIP" .)
  echo "✅ Frontend application built and packaged successfully."
else
  echo "⚠️ Frontend directory '$FRONTEND_DIR' not found. Skipping frontend build."
fi

# --- Final Cleanup ---
echo "Cleaning up temporary build directory..."
rm -rf "$TEMP_BUILD_DIR"

echo "--- ✨ Artifacts successfully created in $ARTIFACTS_DIR ---"
ls -l "$ARTIFACTS_DIR"
