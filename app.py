from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, after_this_request
from werkzeug.exceptions import RequestEntityTooLarge
import os
import json
import time
import traceback
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from config import Config
from extractors.text_extractor import TextExtractor
from extractors.table_extractor import TableExtractor
from extractors.ocr_extractor import OCRExtractor
from extractors.ai_ocr_extractor import AIOCRExtractor
from extractors.image_extractor import ImageExtractor
from utils.pdf_utils import get_pdf_metadata, is_scanned_pdf
from utils.file_handler import allowed_file, save_uploaded_file
from utils.record_parser import parse_elector_records
from utils.elector_summary import extract_elector_summary
from utils.supabase_store import SupabaseStore
import pandas as pd



app = Flask(__name__, static_folder='frontend/dist', static_url_path='')
app.config.from_object(Config)
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')
JOBS = {}
EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get('EXTRACTION_WORKERS', '2')))
SUPABASE = SupabaseStore()
@app.route('/check')
def check():
    import subprocess
    import pytesseract
    try:
        result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True)
        version = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
        return jsonify({
            'tesseract_path': result.stdout.strip(),
            'version': version.stdout.strip(),
            'pytesseract_cmd': pytesseract.pytesseract.tesseract_cmd,
            'ocr_engine': app.config['OCR_ENGINE'],
            'ocr_engine_fallback': app.config['OCR_ENGINE_FALLBACK'],
            'ai_ocr_provider': app.config['AI_OCR_PROVIDER'],
            'gemini_model': app.config['GEMINI_MODEL'],
            'gemini_fallback_models': app.config['GEMINI_FALLBACK_MODELS'],
            'gemini_api_key_configured': bool(app.config['GEMINI_API_KEY']),
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.errorhandler(RequestEntityTooLarge)
def file_too_large(error):
    max_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({'error': f'File is too large. Upload PDFs up to {max_mb} MB, or split the PDF into smaller page ranges.'}), 413
@app.route('/')
def index():
    react_index = os.path.join(FRONTEND_DIST, 'index.html')
    if os.path.exists(react_index):
        return send_from_directory(FRONTEND_DIST, 'index.html')
    return render_template('index.html', asset_version=int(time.time()))

# Configure OCR binary path (helps on Windows when PATH isn't refreshed yet)
try:
    import pytesseract
    tess_cmd = app.config.get('TESSERACT_CMD')
    if tess_cmd and os.path.exists(tess_cmd):
        pytesseract.pytesseract.tesseract_cmd = tess_cmd
except Exception:
    pass


def _parse_page(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        page = int(value)
        return page if page >= 1 else None
    except ValueError:
        return None


def _extraction_options(form):
    try:
        ocr_dpi = int(form.get('ocr_dpi', '150'))
    except ValueError:
        ocr_dpi = 150

    page_from = _parse_page(form.get('page_from'))
    page_to = _parse_page(form.get('page_to'))
    if page_from and page_to and page_to < page_from:
        page_from, page_to = page_to, page_from

    return {
        'extract_text': form.get('extract_text', 'true') == 'true',
        'extract_tables': form.get('extract_tables', 'false') == 'true',
        'extract_images': form.get('extract_images', 'false') == 'true',
        'use_ocr': form.get('use_ocr', 'false') == 'true',
        'ocr_dpi': min(max(ocr_dpi, 100), 300),
        'page_from': page_from,
        'page_to': page_to,
    }


def _limit_ocr_range(page_from, page_to, total_pages):
    max_pages = max(1, int(app.config.get('OCR_MAX_PAGES', 25)))
    start = max(1, int(page_from)) if page_from else 1
    requested_end = min(total_pages, int(page_to)) if page_to else total_pages
    requested_end = max(start, requested_end)
    capped_end = min(requested_end, start + max_pages - 1)

    warning = None
    if capped_end < requested_end:
        warning = (
            f'OCR was limited to pages {start}-{capped_end} in this run. '
            f'Set the next range to {capped_end + 1}-{min(total_pages, capped_end + max_pages)} '
            f'to continue. Max OCR pages per run: {max_pages}.'
        )

    return start, capped_end, warning


def _run_extraction(job_id, filepath, filename, options):
    started_at = time.time()
    JOBS[job_id] = {
        'id': job_id,
        'status': 'running',
        'filename': filename,
        'message': 'Reading metadata',
        'result': None,
        'error': None,
    }

    try:
        page_from = options['page_from']
        page_to = options['page_to']
        metadata = get_pdf_metadata(filepath)
        is_scanned = is_scanned_pdf(filepath)

        results = {
            'id': job_id,
            'filename': filename,
            'metadata': metadata,
            'is_scanned': is_scanned,
            'page_range': {'from': page_from, 'to': page_to},
            'extractions': {},
            'warnings': [],
            'errors': [],
            'timing_ms': {},
            'storage': {},
        }

        if options['use_ocr']:
            total_pages = metadata.get('total_pages', 0) or 1
            page_from, page_to, range_warning = _limit_ocr_range(page_from, page_to, total_pages)
            results['page_range'] = {'from': page_from, 'to': page_to}
            results['warnings'].append(f"OCR engine: {app.config['OCR_ENGINE']}")
            if range_warning:
                results['warnings'].append(range_warning)

        if options['extract_text']:
            try:
                JOBS[job_id]['message'] = 'Extracting text'
                if options['use_ocr']:
                    t0 = time.time()
                    try:
                        def update_ocr_progress(page_num, document_pages):
                            selected_total = max(1, page_to - page_from + 1)
                            selected_index = max(1, page_num - page_from + 1)
                            JOBS[job_id]['message'] = f'OCR page {page_num} ({selected_index} of {selected_total})'

                        if app.config['OCR_ENGINE'] == 'ai':
                            ai_extractor = AIOCRExtractor(
                                filepath,
                                provider=app.config['AI_OCR_PROVIDER'],
                                model=app.config['GEMINI_MODEL'],
                                fallback_models=app.config['GEMINI_FALLBACK_MODELS'],
                                max_retries=app.config['GEMINI_MAX_RETRIES'],
                                retry_backoff_seconds=app.config['GEMINI_RETRY_BACKOFF_SECONDS'],
                                api_key=app.config['GEMINI_API_KEY'],
                            )
                            results['extractions']['text'] = ai_extractor.extract_text_ai(
                                dpi=app.config['AI_OCR_DPI'],
                                page_from=page_from,
                                page_to=page_to,
                                max_image_pixels=app.config['AI_OCR_MAX_IMAGE_PIXELS'],
                                progress_callback=update_ocr_progress,
                            )
                        else:
                            ocr_extractor = OCRExtractor(filepath)
                            results['extractions']['text'] = ocr_extractor.extract_text_ocr(
                                dpi=options['ocr_dpi'],
                                page_from=page_from,
                                page_to=page_to,
                                page_timeout=app.config['TESSERACT_PAGE_TIMEOUT'],
                                tesseract_config=app.config['OCR_TESSERACT_CONFIG'],
                                max_image_pixels=app.config['OCR_MAX_IMAGE_PIXELS'],
                                progress_callback=update_ocr_progress,
                            )
                        results['warnings'].extend(results['extractions']['text'].get('warnings', []))
                        results['timing_ms']['ocr'] = int((time.time() - t0) * 1000)
                    except Exception as ocr_error:
                        if app.config['OCR_ENGINE'] == 'ai' and app.config['OCR_ENGINE_FALLBACK'] == 'tesseract':
                            results['warnings'].append(f'AI OCR unavailable ({ocr_error}). Used Tesseract OCR instead.')
                            ocr_extractor = OCRExtractor(filepath)
                            results['extractions']['text'] = ocr_extractor.extract_text_ocr(
                                dpi=options['ocr_dpi'],
                                page_from=page_from,
                                page_to=page_to,
                                page_timeout=app.config['TESSERACT_PAGE_TIMEOUT'],
                                tesseract_config=app.config['OCR_TESSERACT_CONFIG'],
                                max_image_pixels=app.config['OCR_MAX_IMAGE_PIXELS'],
                                progress_callback=update_ocr_progress,
                            )
                            results['warnings'].extend(results['extractions']['text'].get('warnings', []))
                            results['timing_ms']['ocr'] = int((time.time() - t0) * 1000)
                        else:
                            raise RuntimeError(f"OCR engine '{app.config['OCR_ENGINE']}' failed: {ocr_error}") from ocr_error
                else:
                    text_extractor = TextExtractor(filepath)
                    t0 = time.time()
                    results['extractions']['text'] = text_extractor.extract_all(
                        page_from=page_from,
                        page_to=page_to,
                    )
                    results['timing_ms']['text'] = int((time.time() - t0) * 1000)
                    if is_scanned:
                        results['warnings'].append(
                            'This looks like a scanned PDF. Enable OCR if text output is empty.'
                        )
            except Exception as e:
                results['warnings'].append(f'Text extraction skipped: {str(e)}')
                results['errors'].append({'stage': 'text', 'message': str(e)})

        try:
            text_result = results.get('extractions', {}).get('text', {})
            pages = text_result.get('pages', [])
            summary = extract_elector_summary(pages)
            if summary:
                results['extractions']['elector_summary'] = summary
            ai_records = text_result.get('records', {})
            if ai_records.get('records'):
                JOBS[job_id]['message'] = 'Using AI parsed records'
                results['extractions']['records'] = ai_records
                results['timing_ms']['records'] = 0
            elif pages:
                JOBS[job_id]['message'] = 'Parsing records'
                t0 = time.time()
                results['extractions']['records'] = parse_elector_records(pages)
                results['timing_ms']['records'] = int((time.time() - t0) * 1000)
        except Exception as e:
            results['warnings'].append(f'Record parsing skipped: {str(e)}')
            results['errors'].append({'stage': 'records', 'message': str(e)})

        if options['extract_tables']:
            try:
                JOBS[job_id]['message'] = 'Extracting tables'
                table_extractor = TableExtractor(filepath)
                t0 = time.time()
                results['extractions']['tables'] = table_extractor.extract_all(
                    page_from=page_from,
                    page_to=page_to,
                )
                results['timing_ms']['tables'] = int((time.time() - t0) * 1000)
            except Exception as e:
                results['warnings'].append(f'Table extraction skipped: {str(e)}')
                results['errors'].append({'stage': 'tables', 'message': str(e)})

        if options['extract_images']:
            try:
                JOBS[job_id]['message'] = 'Extracting images'
                with tempfile.TemporaryDirectory() as image_folder:
                    image_extractor = ImageExtractor(filepath, image_folder)
                    t0 = time.time()
                    image_results = image_extractor.extract_images(
                        page_from=page_from,
                        page_to=page_to,
                    )
                    if SUPABASE.enabled and SUPABASE.bucket:
                        for image in image_results.get('images', []):
                            remote_path = f"images/{job_id}/{image['filename']}"
                            image['url'] = SUPABASE.upload_file(
                                image['path'],
                                remote_path,
                                f"image/{image['format']}",
                            )
                            image['path'] = remote_path
                    results['extractions']['images'] = image_results
                    results['timing_ms']['images'] = int((time.time() - t0) * 1000)
            except Exception as e:
                results['warnings'].append(f'Image extraction skipped: {str(e)}')
                results['errors'].append({'stage': 'images', 'message': str(e)})

        results['timing_ms']['total'] = int((time.time() - started_at) * 1000)
        JOBS[job_id]['message'] = 'Saving results'
        results['storage'] = SUPABASE.save_result(job_id, filename, results)
        if results['storage'].get('warning'):
            results['warnings'].append(results['storage']['warning'])

        JOBS[job_id] = {
            'id': job_id,
            'status': 'complete',
            'filename': filename,
            'message': 'Extraction complete',
            'result': results,
            'error': None,
        }
    except Exception as exc:
        traceback.print_exc()
        JOBS[job_id] = {
            'id': job_id,
            'status': 'failed',
            'filename': filename,
            'message': 'Extraction failed',
            'result': None,
            'error': str(exc),
        }
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
        return jsonify({'error': 'Invalid file type. Only PDF is available now'}), 400
    
    try:
        filepath, filename = save_uploaded_file(file, app.config['UPLOAD_FOLDER'])
        job_id = uuid.uuid4().hex
        options = _extraction_options(request.form)
        JOBS[job_id] = {
            'id': job_id,
            'status': 'queued',
            'filename': filename,
            'message': 'Queued for extraction',
            'result': None,
            'error': None,
        }
        EXECUTOR.submit(_run_extraction, job_id, filepath, filename, options)
        return jsonify({'job_id': job_id, 'status': 'queued', 'message': 'Extraction started'}), 202
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/jobs/<job_id>')
def get_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/export/<format>', methods=['POST'])
def export_data(format):
    """Export extracted data in different formats"""
    data = request.json
    
    try:
        if format == 'json':
            output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.json').name
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif format == 'excel':
            output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx').name
            
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                text_pages = data.get('extractions', {}).get('text', {}).get('pages', [])
                records = data.get('extractions', {}).get('records', {}).get('records', [])
                tables = data.get('extractions', {}).get('tables', {}).get('tables', [])

                # Put the most useful extracted data first so Excel opens on it.
                if records:
                    pd.DataFrame(records).to_excel(writer, sheet_name='Extracted_Data', index=False)
                elif text_pages:
                    pd.DataFrame(text_pages).to_excel(writer, sheet_name='Extracted_Data', index=False)
                elif tables:
                    pd.DataFrame(tables[0].get('data', [])).to_excel(writer, sheet_name='Extracted_Data', index=False)
                else:
                    pd.DataFrame([
                        {'field': key, 'value': value}
                        for key, value in data.get('metadata', {}).items()
                    ]).to_excel(writer, sheet_name='Extracted_Data', index=False)

                metadata_df = pd.DataFrame([
                    {'field': key, 'value': value}
                    for key, value in data.get('metadata', {}).items()
                ])
                metadata_df.to_excel(writer, sheet_name='Metadata', index=False)

                # Export text
                if text_pages:
                    text_df = pd.DataFrame(text_pages)
                    text_df.to_excel(writer, sheet_name='Text', index=False)

                # Export parsed records (electoral roll)
                if records:
                    records_df = pd.DataFrame(records)
                    records_df.to_excel(writer, sheet_name='Records', index=False)
                
                # Export tables
                if tables:
                    for table in tables:
                        df = pd.DataFrame(table['data'])
                        sheet_name = f"Table_{table['table_number']}"
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        elif format == 'csv':
            output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.csv').name
            
            # Prefer parsed records, then text pages, table data, or metadata.
            if data.get('extractions', {}).get('records', {}).get('records'):
                records_df = pd.DataFrame(data['extractions']['records']['records'])
                records_df.to_csv(output_path, index=False, encoding='utf-8')
            elif 'text' in data.get('extractions', {}):
                text_df = pd.DataFrame(data['extractions']['text']['pages'])
                text_df.to_csv(output_path, index=False, encoding='utf-8')
            elif data.get('extractions', {}).get('tables', {}).get('tables'):
                first_table = data['extractions']['tables']['tables'][0]
                table_df = pd.DataFrame(first_table.get('data', []))
                table_df.to_csv(output_path, index=False, encoding='utf-8')
            else:
                metadata_df = pd.DataFrame([
                    {'field': key, 'value': value}
                    for key, value in data.get('metadata', {}).items()
                ])
                metadata_df.to_csv(output_path, index=False, encoding='utf-8')
        else:
            return jsonify({'error': 'Unsupported export format'}), 400

        @after_this_request
        def cleanup_export(response):
            try:
                os.remove(output_path)
            except OSError:
                pass
            return response

        download_name = f"extractum-export.{ 'xlsx' if format == 'excel' else format }"
        return send_file(output_path, as_attachment=True, download_name=download_name)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/extracted-image/<filename>')
def extracted_image(filename):
    """Legacy preview fallback for previously uploaded image-like assets."""
    upload_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(upload_image_path):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    return jsonify({'error': 'Image not found. Configure SUPABASE_STORAGE_BUCKET for extracted image previews.'}), 404

@app.route('/assets/<path:filename>')
def react_assets(filename):
    """Serve Vite-built React assets."""
    return send_from_directory(os.path.join(FRONTEND_DIST, 'assets'), filename)

@app.route('/<path:path>')
def react_spa(path):
    """Serve built React files and fall back to the SPA entry."""
    requested_path = os.path.join(FRONTEND_DIST, path)
    if os.path.exists(requested_path) and os.path.isfile(requested_path):
        return send_from_directory(FRONTEND_DIST, path)

    react_index = os.path.join(FRONTEND_DIST, 'index.html')
    if os.path.exists(react_index):
        return send_from_directory(FRONTEND_DIST, 'index.html')

    return render_template('index.html', asset_version=int(time.time()))

if __name__ == '__main__':
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    app.run(host='0.0.0.0', port=port)
