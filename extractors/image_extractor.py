from __future__ import annotations

import os
from typing import Dict

class ImageExtractor:
    def __init__(self, pdf_path: str, output_folder: str = 'output/images'):
        self.pdf_path = pdf_path
        self.output_folder = output_folder
        os.makedirs(output_folder, exist_ok=True)
    
    def extract_images(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract all images from PDF"""
        import fitz  # PyMuPDF

        pdf_document = fitz.open(self.pdf_path)
        images_data = []

        total_pages = len(pdf_document)
        start = max(1, int(page_from)) if page_from else 1
        end = min(total_pages, int(page_to)) if page_to else total_pages

        for page_num in range(start - 1, end):
            page = pdf_document[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                
                # Save image
                image_filename = f"page{page_num + 1}_img{img_index + 1}.{base_image['ext']}"
                image_path = os.path.join(self.output_folder, image_filename)
                
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                images_data.append({
                    'page': page_num + 1,
                    'image_number': img_index + 1,
                    'filename': image_filename,
                    'path': image_path,
                    'width': base_image["width"],
                    'height': base_image["height"],
                    'format': base_image["ext"]
                })
        
        pdf_document.close()
        
        return {
            'total_images': len(images_data),
            'selected_range': {'from': start, 'to': end, 'document_pages': total_pages},
            'images': images_data
        }