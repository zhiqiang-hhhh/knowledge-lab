#!/bin/bash

# Directory containing the .sql files
DIRECTORY="./modified"

# Find all .sql files in the specified directory
for file in "$DIRECTORY"/*.sql; do
    # Use sed to delete comments and blank lines before the first SELECT statement
    sed -i '1,/select/{/select/!d}' "$file"
done
