import os
import io
import re
import json
import logging
import platform
import subprocess
from datetime import datetime
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict, Any, Optional, Tuple

# OpenCVのインポートを条件付きに
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV not available. Advanced image processing will be disabled.")

from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Tesseractのパスを自動検出して設定
def setup_tesseract():
    """Tesseractの実行パスを設定"""
    system = platform.system()
    
    # Windowsの場合
    if system == "Windows":
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\tesseract\tesseract.exe"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logger.info(f"Tesseract found at: {path}")
                return True
    
    # macOSの場合
    elif system == "Darwin":
        possible_paths = [
            "/usr/local/bin/tesseract",
            "/opt/homebrew/bin/tesseract",
            "/usr/bin/tesseract"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logger.info(f"Tesseract found at: {path}")
                return True
    
    # Linuxまたはその他の場合、デフォルトパスを試す
    try:
        # tesseractコマンドが使えるか確認
        result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"Tesseract version: {result.stdout.split()[1]}")
            return True
    except Exception as e:
        logger.error(f"Tesseract not found in PATH: {e}")
    
    return False

# Tesseractのセットアップ
tesseract_available = setup_tesseract()

# Date patterns for Japanese receipts (改善版)
DATE_PATTERNS = [
    # YYYY/MM/DD, YYYY-MM-DD, YYYY年MM月DD日
    r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})',
    # YY/MM/DD, YY-MM-DD, YY年MM月DD日
    r'(\d{2})[/\-年](\d{1,2})[/\-月](\d{1,2})',
    # 令和/平成
    r'令和(\d{1,2})年(\d{1,2})月(\d{1,2})日',
    r'平成(\d{1,2})年(\d{1,2})月(\d{1,2})日',
    # MM/DD形式（年なし）
    r'(\d{1,2})[/\-月](\d{1,2})日?',
    # 2023.05.15形式
    r'(\d{4})\.(\d{1,2})\.(\d{1,2})',
    # 23.05.15形式
    r'(\d{2})\.(\d{1,2})\.(\d{1,2})',
]

# Amount patterns (改善版)
AMOUNT_PATTERNS = [
    # 合計パターン
    r'合計\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'合\s*計\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'計\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    
    # 小計/総額/金額パターン
    r'(?:小計|総額|金額)\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    
    # ¥記号付きパターン
    r'¥\s*(\d{1,3}(?:,\d{3})*)',
    
    # 円付きパターン
    r'(\d{1,3}(?:,\d{3})*)\s*円',
    
    # お預かり/お釣りパターン（レシートによくある）
    r'お預かり\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*)',
    r'お釣り\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*)',
    
    # TOTAL（英語）パターン
    r'TOTAL\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'Total\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    
    # 大きい数字を優先的に取得（最後の手段）
    r'(\d{3,}(?:,\d{3})*)',
]

# Tax patterns
TAX_PATTERNS = [
    r'(税抜|税別)\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'(税込)\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'内税\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
    r'消費税\s*[:：]?\s*¥?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
]

class ReceiptProcessor:
    """Secure receipt processing with fallback OCR functionality."""
    
    def __init__(self):
        """Initialize the receipt processor with secure configuration."""
        self.openai_available = settings.openai_available
        self.tesseract_available = tesseract_available
        self.cv2_available = CV2_AVAILABLE
        
        if not self.tesseract_available:
            logger.error("Tesseract OCR is not available. Please install Tesseract OCR.")
        
        if self.openai_available:
            try:
                self.llm = ChatOpenAI(
                    api_key=settings.openai_api_key,
                    temperature=0,
                    max_retries=3,
                    request_timeout=30.0
                )
                self.prompt = self._create_prompt_template()
                logger.info("OpenAI API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI API: {e}")
                self.openai_available = False
        else:
            logger.info("OpenAI API not available, using fallback OCR processing")
        
        # Configure Tesseract if custom path is provided
        if settings.tessdata_prefix:
            os.environ['TESSDATA_PREFIX'] = settings.tessdata_prefix
        
        # Tesseractの言語データを確認
        self._check_tesseract_languages()
    
    def _check_tesseract_languages(self):
        """Tesseractで利用可能な言語を確認"""
        if not self.tesseract_available:
            return
        
        try:
            langs = pytesseract.get_languages(config='')
            logger.info(f"Available Tesseract languages: {langs}")
            
            if 'jpn' not in langs:
                logger.warning("Japanese language data (jpn) not found in Tesseract. Japanese text recognition may not work.")
            if 'eng' not in langs:
                logger.warning("English language data (eng) not found in Tesseract.")
        except Exception as e:
            logger.error(f"Failed to get Tesseract languages: {e}")
    
    def _create_prompt_template(self) -> ChatPromptTemplate:
        """Create a secure prompt template for OpenAI."""
        return ChatPromptTemplate.from_template(
            """
            以下は日本のレシートのテキストです。このテキストから以下の情報を抽出してください：
            1. 日付 (YYYY-MM-DD形式)
            2. 店名または会社名
            3. 合計金額 (数値のみ)
            4. 税抜き価格 (あれば、数値のみ)
            5. 税込み価格 (あれば、数値のみ)
            
            JSONフォーマットで回答してください：
            {{
                "date": "YYYY-MM-DD",
                "store_name": "店名",
                "total_amount": 数値,
                "tax_excluded_amount": 数値 or null,
                "tax_included_amount": 数値 or null
            }}
            
            レシートテキスト:
            {text}
            """
        )
    
    def _preprocess_image_advanced(self, image: Image.Image) -> Image.Image:
        """画像の前処理を実施（記事を参考に実装）"""
        if not self.cv2_available:
            logger.info("OpenCV not available, using basic preprocessing")
            return self._preprocess_image_basic(image)
            
        try:
            # PIL ImageをOpenCV形式に変換
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # グレースケール変換
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            # ノイズ除去
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            
            # コントラスト調整（CLAHE）
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(denoised)
            
            # 二値化（大津の手法）
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # モルフォロジー変換でノイズを除去
            kernel = np.ones((1,1), np.uint8)
            cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            # 傾き補正
            coords = np.column_stack(np.where(cleaned > 0))
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            
            # 回転補正
            (h, w) = cleaned.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(cleaned, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            
            # OpenCV画像をPIL Imageに変換
            result_image = Image.fromarray(rotated)
            
            logger.info("Advanced image preprocessing completed")
            return result_image
            
        except Exception as e:
            logger.warning(f"Advanced preprocessing failed, using basic method: {e}")
            # 高度な前処理が失敗した場合は基本的な処理にフォールバック
            return self._preprocess_image_basic(image)
    
    def _preprocess_image_basic(self, image: Image.Image) -> Image.Image:
        """基本的な画像前処理"""
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # グレースケール変換
        image = image.convert('L')
        
        # コントラスト強調
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        # シャープネス強調
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)
        
        # Resize if too large
        width, height = image.size
        if width > 2000 or height > 2000:
            ratio = min(2000/width, 2000/height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return image
    
    def process_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Process receipt image and extract information securely."""
        try:
            # Validate image
            if not self._validate_image(image_bytes):
                return {
                    "success": False,
                    "message": "無効な画像ファイルです。JPEGまたはPNG形式の画像をアップロードしてください。",
                    "data": None
                }
            
            # Tesseractが利用できない場合のエラー
            if not self.tesseract_available:
                return {
                    "success": False,
                    "message": "OCRエンジンが利用できません。Tesseract OCRをインストールしてください。",
                    "data": None
                }
            
            # Open image
            image = Image.open(io.BytesIO(image_bytes))
            logger.info(f"Original image size: {image.size}, mode: {image.mode}")
            
            # 前処理を実行（OpenCVが利用可能なら高度な処理、なければ基本的な処理）
            processed_image = self._preprocess_image_advanced(image)
            
            # Extract text using OCR with custom config
            logger.info("Starting OCR processing...")
            
            # Tesseractの設定を最適化
            custom_config = r'--oem 3 --psm 6'  # OEM 3: Default, PSM 6: Uniform block of text
            
            # 日本語と英語の両方を認識
            text = pytesseract.image_to_string(processed_image, lang='jpn+eng', config=custom_config)
            
            # デバッグ用：OCR結果を詳細にログ出力
            logger.info(f"OCR extracted text length: {len(text)}")
            logger.info(f"OCR extracted text (first 500 chars): {text[:500]}")
            logger.debug(f"Full OCR text:\n{text}")
            
            # テキストが空の場合の処理
            if not text.strip():
                logger.warning("OCR returned empty text, trying with different settings")
                # 異なる設定で再試行
                custom_config = r'--oem 1 --psm 3'  # OEM 1: LSTM only, PSM 3: Fully automatic
                text = pytesseract.image_to_string(processed_image, lang='jpn+eng', config=custom_config)
                logger.info(f"Second OCR attempt result length: {len(text)}")
            
            # Process text based on available services
            if self.openai_available and text.strip():
                result = self._extract_with_ai(text)
                if not result["success"]:
                    logger.warning("AI extraction failed, falling back to regex")
                    result = self._extract_with_regex(text)
            else:
                result = self._extract_with_regex(text)
            
            # 日付が抽出できなかった場合、現在の日時を使用
            if result["success"] and result["data"]:
                if not result["data"].get("date"):
                    result["data"]["date"] = datetime.now().strftime("%Y-%m-%d")
                    result["message"] += " 日付は現在の日付で補完しました。"
                    logger.info("Date not found in receipt, using current date")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"画像処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
    
    def _validate_image(self, image_bytes: bytes) -> bool:
        """Validate image format and size."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            # Check format
            if image.format not in ['JPEG', 'PNG']:
                return False
            
            # Check size (max 10MB)
            if len(image_bytes) > 10 * 1024 * 1024:
                return False
            
            # Check dimensions (reasonable limits)
            width, height = image.size
            if width > 5000 or height > 5000:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _extract_with_ai(self, text: str) -> Dict[str, Any]:
        """Extract receipt information using OpenAI API with error handling."""
        try:
            if not text.strip():
                return {
                    "success": False,
                    "message": "OCRでテキストを抽出できませんでした。",
                    "data": None
                }
            
            response = self.llm.invoke(self.prompt.format(text=text))
            result = response.content
            
            # Extract JSON from response
            json_match = re.search(r'{.*}', result, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in AI response")
                return {
                    "success": False,
                    "message": "AI処理でJSONを抽出できませんでした。",
                    "data": None
                }
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Validate required fields
            missing_fields = []
            if not data.get("date"):
                missing_fields.append("日付")
            if not data.get("store_name"):
                missing_fields.append("店名")
            if not data.get("total_amount"):
                missing_fields.append("合計金額")
            
            if missing_fields:
                return {
                    "success": False,
                    "message": f"必要な情報（{', '.join(missing_fields)}）を抽出できませんでした。",
                    "data": None
                }
            
            # Process and validate data
            processed_data = {
                "date": data.get("date"),
                "store_name": data.get("store_name"),
                "total_amount": float(data.get("total_amount")),
                "tax_excluded_amount": float(data.get("tax_excluded_amount")) if data.get("tax_excluded_amount") else None,
                "tax_included_amount": float(data.get("tax_included_amount")) if data.get("tax_included_amount") else None,
                "expense_category": None
            }
            
            return {
                "success": True,
                "message": "AI処理でレシート情報を抽出しました。",
                "data": processed_data
            }
            
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from AI response")
            return {
                "success": False,
                "message": "AI処理のレスポンスが無効でした。",
                "data": None
            }
        except Exception as e:
            logger.error(f"AI extraction error: {e}")
            return {
                "success": False,
                "message": "AI処理中にエラーが発生しました。",
                "data": None
            }
    
    def _extract_with_regex(self, text: str) -> Dict[str, Any]:
        """Extract receipt information using regex patterns as fallback."""
        try:
            # テキストが空の場合
            if not text.strip():
                return {
                    "success": False,
                    "message": "OCRでテキストを抽出できませんでした。画像の品質を確認してください。",
                    "data": None
                }
            
            date_str = self._extract_date(text)
            store_name = self._extract_store_name(text)
            total_amount = self._extract_amount(text)
            tax_excluded, tax_included = self._extract_tax_amounts(text)
            
            missing_fields = []
            if not date_str:
                missing_fields.append("日付")
            if not store_name:
                missing_fields.append("店名")
            if not total_amount:
                missing_fields.append("合計金額")
            
            # デバッグログ
            logger.info(f"Regex extraction results - Date: {date_str}, Store: {store_name}, Amount: {total_amount}")
            
            if missing_fields:
                return {
                    "success": False,
                    "message": f"必要な情報（{', '.join(missing_fields)}）を抽出できませんでした。画像の品質を確認し、再度お試しください。",
                    "data": None
                }
            
            return {
                "success": True,
                "message": "OCR処理でレシート情報を抽出しました。",
                "data": {
                    "date": date_str,
                    "store_name": store_name,
                    "total_amount": total_amount,
                    "tax_excluded_amount": tax_excluded,
                    "tax_included_amount": tax_included,
                    "expense_category": None
                }
            }
            
        except Exception as e:
            logger.error(f"Regex extraction error: {e}")
            return {
                "success": False,
                "message": "正規表現処理中にエラーが発生しました。",
                "data": None
            }
    
    def _extract_date(self, text: str) -> Optional[str]:
        """Extract date from receipt text."""
        current_year = datetime.now().year
        
        for pattern in DATE_PATTERNS:
            matches = re.search(pattern, text)
            if matches:
                try:
                    if "令和" in pattern:
                        year = 2018 + int(matches.group(1))
                        month = int(matches.group(2))
                        day = int(matches.group(3))
                    elif "平成" in pattern:
                        year = 1988 + int(matches.group(1))
                        month = int(matches.group(2))
                        day = int(matches.group(3))
                    elif len(matches.groups()) == 2:  # MM/DD形式
                        year = current_year
                        month = int(matches.group(1))
                        day = int(matches.group(2))
                    else:
                        year = int(matches.group(1))
                        month = int(matches.group(2))
                        day = int(matches.group(3))
                        
                        if year < 100:
                            year += 2000 if year < 50 else 1900
                    
                    date_obj = datetime(year, month, day)
                    return date_obj.strftime("%Y-%m-%d")
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_store_name(self, text: str) -> Optional[str]:
        """Extract store name from receipt text."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Try to find a line that looks like a store name (first few lines, no numbers)
        for i in range(min(10, len(lines))):  # 最初の10行をチェック
            line = lines[i]
            # 店名らしい行を探す（数字が少なく、長すぎない）
            if line and len(line) > 1 and len(line) < 50:
                # 数字の割合が30%未満の行を店名候補とする
                digit_count = sum(1 for char in line if char.isdigit())
                if len(line) > 0 and digit_count / len(line) < 0.3:
                    # Remove common OCR artifacts
                    cleaned = re.sub(r'[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', line)
                    if cleaned and len(cleaned) > 1:
                        return cleaned
        
        # Fallback: return first non-empty line
        for line in lines:
            if line and len(line) > 1:
                return line[:50]  # 最大50文字
        
        return None
    
    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract total amount from receipt text."""
        amounts_found = []
        
        # すべてのパターンでマッチを試みる
        for pattern in AMOUNT_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # マッチ結果から数値を抽出
                    if isinstance(match, tuple):
                        amount_str = match[0]
                    else:
                        amount_str = match
                    
                    # カンマを削除して数値に変換
                    amount_str = amount_str.replace(',', '')
                    amount = float(amount_str)
                    
                    # 妥当な金額範囲かチェック（1円〜1000万円）
                    if 1 <= amount <= 10000000:
                        amounts_found.append((amount, pattern))
                except (ValueError, IndexError):
                    continue
        
        # 見つかった金額から最も妥当なものを選択
        if amounts_found:
            # 「合計」パターンに一致したものを優先
            for amount, pattern in amounts_found:
                if '合計' in pattern or 'TOTAL' in pattern.upper():
                    return amount
            
            # それ以外は最大値を返す（通常、レシートの合計金額は最大値）
            return max(amounts_found, key=lambda x: x[0])[0]
        
        return None
    
    def _extract_tax_amounts(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract tax excluded and included amounts from receipt text."""
        tax_excluded = None
        tax_included = None
        
        for pattern in TAX_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        if len(match) >= 2:
                            tax_type = match[0]
                            amount_str = match[1]
                        else:
                            amount_str = match[0]
                            tax_type = ""
                    else:
                        amount_str = match
                        tax_type = ""
                    
                    amount_str = amount_str.replace(',', '')
                    amount = float(amount_str)
                    
                    if "税抜" in tax_type or "税別" in tax_type:
                        tax_excluded = amount
                    elif "税込" in tax_type:
                        tax_included = amount
                except (ValueError, IndexError):
                    continue
        
        return tax_excluded, tax_included
