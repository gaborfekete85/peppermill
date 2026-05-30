#!/usr/bin/env bash

set -e

# Get the current git branch name
CURRENT_BRANCH=$(git branch --show-current)

if [ -z "$CURRENT_BRANCH" ]; then
  echo "Error: Could not determine the current git branch." >&2
  exit 1
fi

if [ "$CURRENT_BRANCH" = "main" ]; then
  echo "Error: You are currently on the 'main' branch. Cannot create a PR from main into main." >&2
  exit 1
fi

echo "Creating pull request for '${CURRENT_BRANCH}' into 'main'..."

# Create the pull request
gh pr create \
  --base main \
  --head "$CURRENT_BRANCH" \
  --title "PR: $CURRENT_BRANCH -> main" \
  --body "Automated pull request from $CURRENT_BRANCH to main."

echo "Merging pull request..."

# Merge the pull request
gh pr merge "$CURRENT_BRANCH" --squash --delete-branch=false