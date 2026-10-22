"""
Assemble the complete final project report in Microsoft Word (.docx) format
and export to PDF via Microsoft Word automation.
"""

import os
import sys
import docx
from docx import Document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_helpers import setup_document_styles_and_margins
from build_report_part1 import create_cover_page, configure_header_footer, create_abstract_and_acknowledgements, create_table_of_contents_and_lists
from build_report_part2 import build_chapter_1, build_chapter_2, build_chapter_3, build_chapter_4, build_chapter_5
from build_report_part3 import build_chapter_6, build_chapter_7, build_chapter_8
from build_report_part4 import build_chapter_9, build_chapter_10, build_chapter_11_and_12

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DOCX = os.path.join(PROJECT_DIR, "The_Cloud_Scraper_Final_Project_Report.docx")
OUTPUT_PDF = os.path.join(PROJECT_DIR, "The_Cloud_Scraper_Final_Project_Report.pdf")


def generate_word_report():
    print("=" * 70)
    print("INITIALIZING THE CLOUD SCRAPER FINAL PROJECT REPORT GENERATOR")
    print("=" * 70)
    
    doc = Document()
    setup_document_styles_and_margins(doc)
    
    print("[1/5] Creating Cover Page & Configuring Running Headers/Footers...")
    create_cover_page(doc)
    configure_header_footer(doc)
    
    print("[2/5] Creating Abstract, Acknowledgements, and Lists...")
    create_abstract_and_acknowledgements(doc)
    create_table_of_contents_and_lists(doc)
    
    print("[3/5] Building Chapters 1 through 5 (Introduction to Architecture)...")
    build_chapter_1(doc)
    build_chapter_2(doc)
    build_chapter_3(doc)
    build_chapter_4(doc)
    build_chapter_5(doc)
    
    print("[4/5] Building Chapters 6 through 8 (Implementation, Tech Stack, Testing)...")
    build_chapter_6(doc)
    build_chapter_7(doc)
    build_chapter_8(doc)
    
    print("[5/5] Building Chapters 9 through 12, References, and Appendices...")
    build_chapter_9(doc)
    build_chapter_10(doc)
    build_chapter_11_and_12(doc)
    
    doc.save(OUTPUT_DOCX)
    print(f"SUCCESS: Report successfully saved to: {OUTPUT_DOCX}")
    file_size_kb = os.path.getsize(OUTPUT_DOCX) / 1024
    print(f"File Size: {file_size_kb:.2f} KB")


def convert_docx_to_pdf_via_word():
    """Convert .docx to .pdf using Microsoft Word COM automation, updating fields."""
    print("=" * 70)
    print("CONVERTING DOCX TO PDF VIA MICROSOFT WORD COM AUTOMATION")
    print("=" * 70)
    
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        
        print(f"Opening {OUTPUT_DOCX} in Word...")
        doc = word.Documents.Open(os.path.abspath(OUTPUT_DOCX))
        
        print("Updating all document fields (TOC, page numbers)...")
        doc.Fields.Update()
        
        print(f"Exporting to PDF: {OUTPUT_PDF}...")
        # 17 = wdFormatPDF
        doc.SaveAs2(os.path.abspath(OUTPUT_PDF), FileFormat=17)
        doc.Close()
        word.Quit()
        
        pdf_size_kb = os.path.getsize(OUTPUT_PDF) / 1024
        print(f"SUCCESS: PDF successfully generated: {OUTPUT_PDF} ({pdf_size_kb:.2f} KB)")
    except Exception as e:
        print(f"Note: Word COM automation encountered an issue: {e}")
        print("The .docx file is fully preserved and complete.")


if __name__ == "__main__":
    generate_word_report()
    convert_docx_to_pdf_via_word()
