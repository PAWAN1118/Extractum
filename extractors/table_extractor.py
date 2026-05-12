from __future__ import annotations

from typing import Dict, List

import pandas as pd

class TableExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def _pages_arg(self, page_from: int | None, page_to: int | None) -> str:
        if page_from and page_to:
            start = max(1, int(page_from))
            end = max(start, int(page_to))
            return f"{start}-{end}"
        if page_from and not page_to:
            start = max(1, int(page_from))
            return str(start)
        return "all"
    
    def extract_with_camelot(self, pages='all') -> List[pd.DataFrame]:
        """Extract tables using Camelot (better for complex tables)"""
        try:
            import camelot
            tables = camelot.read_pdf(self.pdf_path, pages=pages, flavor='lattice')
            return [table.df for table in tables]
        except Exception as e:
            print(f"Camelot lattice failed: {e}, trying stream")
            try:
                import camelot
                tables = camelot.read_pdf(self.pdf_path, pages=pages, flavor='stream')
                return [table.df for table in tables]
            except Exception as e2:
                print(f"Camelot stream also failed: {e2}")
                return []
    
    def extract_with_tabula(self, pages='all') -> List[pd.DataFrame]:
        """Extract tables using Tabula (fallback)"""
        try:
            import tabula
            tables = tabula.read_pdf(self.pdf_path, pages=pages, multiple_tables=True)
            return tables if isinstance(tables, list) else [tables]
        except Exception as e:
            print(f"Tabula failed: {e}")
            return []
    
    def extract_all(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract tables using both methods"""
        pages = self._pages_arg(page_from, page_to)
        camelot_tables = self.extract_with_camelot(pages=pages)
        
        if not camelot_tables:
            camelot_tables = self.extract_with_tabula(pages=pages)
        
        tables_data = []
        for idx, table in enumerate(camelot_tables, 1):
            tables_data.append({
                'table_number': idx,
                'rows': len(table),
                'columns': len(table.columns),
                'data': table.to_dict('records'),
                'headers': table.columns.tolist()
            })
        
        return {
            'total_tables': len(tables_data),
            'selected_pages': pages,
            'tables': tables_data
        }
