# testing_frontend (Streamlit)

Single-file Streamlit app to manually run and inspect PR analysis with agent context.

## Requirements

- Python 3.10+
- Install dependencies:

```bash
pip install streamlit requests
```

## Run

```bash
cd testing_frontend
streamlit run app.py
```

## Features

- Input GitHub owner/repo/pr_number
- Manual background trigger via `/analyze`
- Full workflow context via `/debug/analyze`
- Shows PR context, file_contexts, memory_context_text
- Shows agent results and findings (per agent)

## Notes

- Does not touch `frontend/` folder.
- Uses FastAPI endpoints from `app/main.py`.
