# PDF Extractor (Flask)

Simple professional UI for extracting **text, tables, images, and metadata** from PDFs.

## Run (Windows / PowerShell)

```powershell
.\run.ps1
```

Then open `http://127.0.0.1:5000`.

## Notes (important on Windows)

- **Always run using `.venv`** (the included `run.ps1` does this). If you run `python app.py` directly, you may see `ModuleNotFoundError` because your global Python doesn’t have the packages installed.
- **OCR** requires the Tesseract binary installed and available in `PATH`.
- **Poppler**: if it’s missing, OCR will still work because the app falls back to **PyMuPDF rendering** automatically.
- **tabula-py** requires Java installed.
- **camelot** may require additional system dependencies depending on mode.

## Supabase result storage

Set these environment variables in Render:

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_RESULTS_TABLE=extraction_results
SUPABASE_STORAGE_BUCKET=pdf-extractor
```

Create the results table:

```sql
create table if not exists extraction_results (
  id text primary key,
  filename text not null,
  result jsonb not null,
  created_at timestamptz default now()
);
```

`SUPABASE_STORAGE_BUCKET` is optional, but if you set it the app also uploads result JSON and extracted images there. Exports are created as temporary downloads and are no longer saved in the local `output` folder.
