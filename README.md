To run the code:

If Homebrew (a package manager) is not installed, run the below in terminal.
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

then if uv isn't installed run (can't hurt to run this again if unsure)
```bash
brew install uv
```

cd into the repository locally, then run:
```bash
uv run main.py
```