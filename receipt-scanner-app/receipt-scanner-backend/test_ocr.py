#!/usr/bin/env python3
"""
OCR動作確認用テストスクリプト
使い方: python test_ocr.py [画像ファイルパス]
"""

import sys
import os
import pytesseract
from PIL import Image
import platform

def setup_tesseract():
    """Tesseractのパスを設定"""
    system = platform.system()
    
    if system == "Windows":
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\tesseract\tesseract.exe"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                print(f"Tesseract found at: {path}")
                return True
    
    elif system == "Darwin":
        possible_paths = [
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
            "/usr/bin/tesseract"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                print(f"Tesseract found at: {path}")
                return True
    
    # デフォルトパスを試す
    try:
        import subprocess
        result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Tesseract version: {result.stdout.split()[1]}")
            return True
    except Exception as e:
        print(f"Tesseract not found: {e}")
    
    return False

def check_tesseract_languages():
    """利用可能な言語をチェック"""
    try:
        langs = pytesseract.get_languages(config='')
        print(f"Available languages: {langs}")
        
        if 'jpn' not in langs:
            print("⚠️  WARNING: Japanese language data (jpn) not found!")
            print("   Install with: sudo apt-get install tesseract-ocr-jpn")
        else:
            print("✅ Japanese language data (jpn) is available")
            
        if 'eng' not in langs:
            print("⚠️  WARNING: English language data (eng) not found!")
        else:
            print("✅ English language data (eng) is available")
            
    except Exception as e:
        print(f"Failed to get languages: {e}")

def test_ocr(image_path):
    """OCRをテスト"""
    try:
        # 画像を開く
        print(f"\nOpening image: {image_path}")
        image = Image.open(image_path)
        print(f"Image size: {image.size}, mode: {image.mode}")
        
        # 基本的なOCR
        print("\n--- Basic OCR (jpn+eng) ---")
        text1 = pytesseract.image_to_string(image, lang='jpn+eng')
        print(f"Extracted text length: {len(text1)}")
        print("First 500 characters:")
        print(text1[:500])
        
        # 設定を変えてOCR
        print("\n--- OCR with custom config (PSM 6) ---")
        text2 = pytesseract.image_to_string(image, lang='jpn+eng', config='--oem 3 --psm 6')
        print(f"Extracted text length: {len(text2)}")
        print("First 500 characters:")
        print(text2[:500])
        
        # 日本語のみ
        print("\n--- Japanese only OCR ---")
        text3 = pytesseract.image_to_string(image, lang='jpn')
        print(f"Extracted text length: {len(text3)}")
        print("First 500 characters:")
        print(text3[:500])
        
    except Exception as e:
        print(f"Error during OCR: {e}")

def main():
    print("=== OCR Test Script ===")
    
    # Tesseractのセットアップ
    if not setup_tesseract():
        print("❌ Tesseract OCR is not installed or not found!")
        print("Please install Tesseract OCR:")
        print("  Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-jpn")
        print("  macOS: brew install tesseract tesseract-lang")
        print("  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
        sys.exit(1)
    
    # 言語データの確認
    check_tesseract_languages()
    
    # 画像パスの取得
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # デフォルトのテスト画像を探す
        possible_paths = [
            "test_receipt.jpg",
            "test_receipt.png",
            "レシート.jpg",
            "receipt.jpg",
            "receipt.png"
        ]
        image_path = None
        for path in possible_paths:
            if os.path.exists(path):
                image_path = path
                break
        
        if not image_path:
            print("\nNo image file specified!")
            print("Usage: python test_ocr.py [image_path]")
            print("Or place a test image named 'test_receipt.jpg' in the current directory")
            sys.exit(1)
    
    # OCRテスト
    if os.path.exists(image_path):
        test_ocr(image_path)
    else:
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
