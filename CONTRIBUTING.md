# Contributing to Aegis Finance

Thanks for your interest in contributing! Aegis Finance is an open-source market intelligence platform — contributions of all kinds are welcome.

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 20+
- A free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)

### Local Setup

```bash
# Clone
git clone https://github.com/Murathanx12/Aegis-Finance.git
cd aegis-finance

# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit .env and add your FRED_API_KEY
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Docker Setup

```bash
cp .env.example .env
# Edit .env and add your FRED_API_KEY
docker compose up --build
```

## How to Contribute

### Report Bugs
Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Browser/OS information

### Suggest Features
Open an issue tagged `enhancement` with:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### Submit Code

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes
4. Run tests: `cd backend && python -m pytest tests/ -v`
5. Commit with conventional format: `feat: add new chart component`
6. Push and open a Pull Request

### Commit Convention

```
feat: description      # New feature
fix: description       # Bug fix
refactor: description  # Code restructuring
docs: description      # Documentation
test: description      # Tests
chore: description     # Dependencies, config
```

## Project Structure

- **`backend/`** — FastAPI services. Most contribution opportunities here.
- **`frontend/`** — Next.js UI. Great for design/UX contributions.
- **`engine/`** — Offline ML training + research. For data science contributors.
- **`docs/`** — Methodology documentation. Always welcome.

## Code Style

- **Python:** Follow PEP 8. Type hints on all function signatures. Use `ruff` for linting.
- **TypeScript:** Follow the existing patterns. Use `prettier` for formatting.
- **No hardcoded values** — all parameters go in `backend/config.py`.

## Disclaimer

Aegis Finance is an educational tool, not financial advice. All predictions are probabilistic estimates with significant uncertainty. Contributors should not make claims about investment outcomes.
