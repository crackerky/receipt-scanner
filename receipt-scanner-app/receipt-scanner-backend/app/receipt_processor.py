import os
import io
import logging
import platform
import subprocess
import base64
from datetime import datetime
from PIL import Image, ImageFilter, ImageEnhance
from typing import Dict, Any, Optional, Tuple
from openai import OpenAI

# HEIFのインポートを条件付きに
try:
    import pyheif
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False
    logging.warning("pyheif not available. HEIC/HEIF image support will be disabled.")

# OpenCVのインポートを条件付きに
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV not available. Advanced image processing will be disabled.")

import pytesseract
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from openai import OpenAI

from app.config import settings
from app.ocr_processor import OCRProcessor
from app.ai_processor import AIProcessor

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


class ReceiptProcessor:
"""Secure receipt processing with AI-OCR Vision and fallback OCR functionality."""

    
    def __init__(self):
        """Initialize the receipt processor with secure configuration."""
        self.openai_available = settings.openai_available
        self.vision_api_available = settings.vision_api_available
        self.tesseract_available = tesseract_available
        self.cv2_available = CV2_AVAILABLE
        self.heif_available = HEIF_AVAILABLE
        

        
        # OCRプロセッサーの初期化
        self.ocr_processor = OCRProcessor(cv2_available=self.cv2_available)
        
        # AIプロセッサーの初期化        # 処理モード設定
        self.processing_mode = self._determine_processing_mode()

        # Initialize OpenAI client for Vision API
        if self.vision_api_available:
            try:
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                logger.info("OpenAI Vision API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI Vision API: {e}")
                self.vision_api_available = False
        
        if not self.tesseract_available:
            logger.error("Tesseract OCR is not available. Please install Tesseract OCR.")

        self.ai_processor = None
        if self.openai_available:
            try:
                self.ai_processor = AIProcessor(
                    api_key=settings.openai_api_key,
                    model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
                )
                logger.info("AI processor initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AI processor: {e}")
                self.openai_available = False
        
        # OpenAI Vision API用のクライアント初期化
        self.openai_client = None
        if self.openai_available:
            try:
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                logger.info("OpenAI client initialized for Vision API")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        
        # Configure Tesseract if custom path is provided
        if settings.tessdata_prefix:
            os.environ['TESSDATA_PREFIX'] = settings.tessdata_prefix
        
        # Tesseractの言語データを確認
        self._check_tesseract_languages()
        
        logger.info(f"Receipt processor initialized - Mode: {self.processing_mode}")
    
    def _determine_processing_mode(self) -> str:
        """処理モードを決定"""
        if not self.tesseract_available:
            return "unavailable"
        elif self.openai_available:
            return "ai-ocr"  # AI-OCR ハイブリッドモード
        else:
            return "ocr-only"  # OCRのみモード
    
    def _check_tesseract_languages(self):
        """Tesseractで利用可能な言語を確認"""
        if not self.tesseract_available:
            return
        
        try:
            langs = pytesseract.get_languages(config='')
            logger.info(f"Available Tesseract languages: {langs}")
            
            if 'jpn' not in langs:
                logger.warning("Japanese language data (jpn) not found in Tesseract.")
            if 'eng' not in langs:
                logger.warning("English language data (eng) not found in Tesseract.")
        except Exception as e:
            logger.error(f"Failed to get Tesseract languages: {e}")
    
    def _create_prompt_template(self) -> ChatPromptTemplate:
        """Create a secure prompt template for OpenAI."""
        return ChatPromptTemplate.from_template(
            """
            以下は日本のレシートのテキストです。このテキストから以下の情報を抽出してください：
            1. 日付 (YYYY-MM-DD形式、見つからない場合はnull)
            2. 店名または会社名
            3. 合計金額 (数値のみ、見つからない場合はnull)
            4. 税抜き価格 (あれば、数値のみ)
            5. 税込み価格 (あれば、数値のみ)
            
            JSONフォーマットで回答してください：
            {{
                "date": "YYYY-MM-DD" or null,
                "store_name": "店名",
                "total_amount": 数値 or null,
                "tax_excluded_amount": 数値 or null,
                "tax_included_amount": 数値 or null
            }}
            
            レシートテキスト:
            {text}
            """
        )
    
    def _create_vision_prompt(self) -> str:
        """Create a prompt for Vision API OCR."""
        return """
        この画像は日本のレシートです。以下の情報を正確に抽出してください：
        
        1. 日付 (YYYY-MM-DD形式、見つからない場合はnull)
        2. 店名または会社名
        3. 合計金額 (数値のみ、見つからない場合はnull)
        4. 税抜き価格 (あれば、数値のみ)
        5. 税込み価格 (あれば、数値のみ)
        
        以下のJSONフォーマットで回答してください：
        {
            "date": "YYYY-MM-DD" or null,
            "store_name": "店名",
            "total_amount": 数値 or null,
            "tax_excluded_amount": 数値 or null,
            "tax_included_amount": 数値 or null
        }
        
        注意事項：
        - 日付は必ずYYYY-MM-DD形式に変換してください
        - 金額は数値のみ（カンマや円記号は除く）
        - 税抜き/税込み価格が明記されていない場合はnull
        - 不明な情報はnullとしてください
        """
    
    def _extract_with_vision_api(self, image_bytes: bytes) -> Dict[str, Any]:
        """Extract receipt information using GPT-4o Vision API."""
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            logger.info("Sending image to Vision API for OCR...")
            
            # Call Vision API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # or "gpt-4o-mini" for cost savings
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self._create_vision_prompt()
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"  # Use "high" for better OCR accuracy
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                response_format={"type": "json_object"}  # Ensure JSON response
            )
            
            # Parse the response
            result_text = response.choices[0].message.content
            logger.info(f"Vision API response: {result_text}")
            
            # Parse JSON response
            data = json.loads(result_text)
            
            # Validate and process the data
            processed_data = {
                "date": data.get("date"),
                "store_name": data.get("store_name"),
                "total_amount": float(data.get("total_amount")) if data.get("total_amount") else None,
                "tax_excluded_amount": float(data.get("tax_excluded_amount")) if data.get("tax_excluded_amount") else None,
                "tax_included_amount": float(data.get("tax_included_amount")) if data.get("tax_included_amount") else None,
                "expense_category": None
            }
            
            # Validate required fields
            if not processed_data.get("store_name"):
                return {
                    "success": False,
                    "message": "Vision APIで店名を抽出できませんでした。",
                    "data": None
                }
            
            logger.info("Successfully extracted receipt data with Vision API")
            
            return {
                "success": True,
                "message": "AI-OCR (Vision API)でレシート情報を抽出しました。",
                "data": processed_data
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Vision API response: {e}")
            return {
                "success": False,
                "message": "Vision APIのレスポンスが無効でした。",
                "data": None
            }
        except Exception as e:
            logger.error(f"Vision API extraction error: {e}")
            return {
                "success": False,
                "message": f"Vision API処理中にエラーが発生しました: {str(e)}",
                "data": None
            }

    def _convert_heic_to_jpeg(self, image_bytes: bytes) -> bytes:
        """Convert HEIC/HEIF image to JPEG format."""
        if not self.heif_available:
            raise ValueError("HEIC conversion not available. Please install pyheif.")
        
        try:
            heif_file = pyheif.read(image_bytes)
            image = Image.frombytes(
                heif_file.mode, 
                heif_file.size, 
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save as JPEG
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=95)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"HEIC conversion failed: {e}")
            raise
    
    def process_image_with_vision(self, image_bytes: bytes) -> Dict[str, Any]:
        """OpenAI Vision APIを使用して画像を直接処理"""
        if not self.openai_client:
            return {
                "success": False,
                "message": "OpenAI Vision APIが利用できません。",
                "data": None
            }
        
        try:
            # 画像をbase64エンコード
            import base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Vision APIを使用
            response = self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """このレシート画像から以下の情報を抽出してJSON形式で返してください：
                                1. 日付 (YYYY-MM-DD形式)
                                2. 店名
                                3. 合計金額
                                4. 税抜き価格（あれば）
                                5. 税込み価格（あれば）
                                6. 商品明細（商品名と価格のリスト）
                                7. 支払い方法
                                
                                JSONフォーマット:
                                {
                                    "date": "YYYY-MM-DD",
                                    "store_name": "店名",
                                    "total_amount": 数値,
                                    "tax_excluded_amount": 数値,
                                    "tax_included_amount": 数値,
                                    "items": [{"name": "商品名", "price": 数値}],
                                    "payment_method": "支払い方法"
                                }"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            
            # レスポンスをパース
            content = response.choices[0].message.content
            import json
            import re
            
            # JSONを抽出
            json_match = re.search(r'{.*}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                
                # データの整形
                processed_data = {
                    "date": data.get("date"),
                    "store_name": data.get("store_name"),
                    "total_amount": float(data.get("total_amount", 0)) if data.get("total_amount") else None,
                    "tax_excluded_amount": float(data.get("tax_excluded_amount", 0)) if data.get("tax_excluded_amount") else None,
                    "tax_included_amount": float(data.get("tax_included_amount", 0)) if data.get("tax_included_amount") else None,
                    "items": data.get("items", []),
                    "payment_method": data.get("payment_method"),
                    "expense_category": self._suggest_category(data),
                    "processing_method": "vision-api"
                }
                
                return {
                    "success": True,
                    "message": "Vision APIでレシート情報を抽出しました。",
                    "data": processed_data
                }
            
            return {
                "success": False,
                "message": "Vision APIの応答を解析できませんでした。",
                "data": None
            }
            
        except Exception as e:
            logger.error(f"Vision API processing error: {e}")
            return {
                "success": False,
                "message": f"Vision API処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
    
    def process_image(self, image_bytes: bytes, processing_mode: Optional[str] = None) -> Dict[str, Any]:
        """
        レシート画像を処理して情報を抽出
        
        Args:
            image_bytes: 画像データ
            processing_mode: 処理モード ('ai', 'ocr', 'vision', 'auto')
        """
        try:
            # HEIC変換を試みる
            if len(image_bytes) >= 12 and image_bytes[4:8] == b'ftyp':
                logger.info("HEIC format detected, attempting conversion")
                try:
                    if self.heif_available:
                        image_bytes = self._convert_heic_to_jpeg(image_bytes)
                        logger.info("HEIC conversion successful")
                    else:
                        logger.warning("HEIC conversion not available")
                except Exception as e:
                    logger.error(f"HEIC conversion failed: {e}")
                    return {
                        "success": False,
                        "message": "HEIC画像の変換に失敗しました。",
                        "data": None
                    }
            
            # 画像検証
            if not self._validate_image(image_bytes):
                return {
                    "success": False,
                    "message": "無効な画像ファイルです。",
                    "data": None
                }
            
            # 処理モードの決定
            if not processing_mode:
                processing_mode = "auto"

            # Try Vision API first if available
            if self.vision_api_available:
                logger.info("Attempting AI-OCR with Vision API...")
                result = self._extract_with_vision_api(image_bytes)
                if result["success"]:
                    # 日付が抽出できなかった場合、現在の日時を使用
                    if result["data"] and not result["data"].get("date"):
                        result["data"]["date"] = datetime.now().strftime("%Y-%m-%d")
                        result["message"] += " 日付は現在の日付で補完しました。"
                    return result
                else:
                    logger.warning("Vision API failed, falling back to traditional OCR")

            # Fall back to traditional OCR processing
            # Tesseractが利用できない場合のエラー
            if not self.tesseract_available:
                return {
                    "success": False,
                    "message": "OCRエンジンが利用できません。Tesseract OCRをインストールしてください。",
                    "data": None
                }

            
            # Vision APIモードの場合
            if processing_mode == "vision" and self.openai_client:
                return self.process_image_with_vision(image_bytes)
            
            # Tesseractが利用できない場合
            if not self.tesseract_available:
                # Vision APIが使える場合はそちらを使用
                if self.openai_client:
                    return self.process_image_with_vision(image_bytes)
                else:
                    return {
                        "success": False,
                        "message": "OCRエンジンが利用できません。",
                        "data": None
                    }
            
            # 画像を開く
            image = Image.open(io.BytesIO(image_bytes))
            logger.info(f"Image opened - size: {image.size}, mode: {image.mode}")
            
            # OCRで画像からテキストを抽出
            processed_image = self.ocr_processor.preprocess_image(image)
            ocr_text = self.ocr_processor.extract_text(processed_image)
            
            logger.info(f"OCR extracted {len(ocr_text)} characters")
            
            # 処理モードに基づいて情報を抽出
            if processing_mode == "ocr" or not self.openai_available:
                # OCRのみで処理
                result = self.ocr_processor.process_receipt_text(ocr_text)
                result["processing_method"] = "ocr"
            
            elif processing_mode == "ai" and self.ai_processor:
                # AIのみで処理
                result = self.ai_processor.process_text(ocr_text)
                result["processing_method"] = "ai"
            
            else:  # auto mode - AI-OCR ハイブリッド
                result = self._hybrid_processing(ocr_text, image)
                result["processing_method"] = "ai-ocr-hybrid"
            
            # 日付が抽出できなかった場合、現在の日付を使用
            if result["success"] and result["data"]:
                if not result["data"].get("date"):
                    result["data"]["date"] = datetime.now().strftime("%Y-%m-%d")
                    result["message"] += " 日付は現在の日付で補完しました。"
                
                # 処理メタデータを追加
                result["data"]["processed_at"] = datetime.utcnow().isoformat()
                result["data"]["processing_info"] = {
                    "method": result.get("processing_method", "unknown"),
                    "ocr_available": self.tesseract_available,
                    "ai_available": self.openai_available,
                    "vision_available": bool(self.openai_client),
                    "cv2_available": self.cv2_available,
                    "heif_support": self.heif_available
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"画像処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
    
    def _hybrid_processing(self, ocr_text: str, image: Image.Image) -> Dict[str, Any]:
        """AI-OCR ハイブリッド処理"""
        # まずAIで処理を試みる
        if self.ai_processor and ocr_text.strip():
            ai_result = self.ai_processor.process_text(ocr_text)
            
            if ai_result["success"]:
                # AIが成功した場合、OCRで補完
                ocr_result = self.ocr_processor.process_receipt_text(ocr_text)
                
                if ocr_result["success"] and ocr_result["data"]:
                    # OCRの結果で補完
                    ai_data = ai_result["data"]
                    ocr_data = ocr_result["data"]
                    
                    # 日付の補完
                    if not ai_data.get("date") and ocr_data.get("date"):
                        ai_data["date"] = ocr_data["date"]
                    
                    # 金額の検証
                    if ai_data.get("total_amount") and ocr_data.get("total_amount"):
                        # 金額が大きく異なる場合は警告
                        diff_ratio = abs(ai_data["total_amount"] - ocr_data["total_amount"]) / max(ai_data["total_amount"], ocr_data["total_amount"])
                        if diff_ratio > 0.1:  # 10%以上の差
                            ai_data["amount_verification_warning"] = True
                            ai_data["ocr_amount"] = ocr_data["total_amount"]
                    
                    # 信頼度の統合
                    ai_confidence = ai_data.get("ai_confidence", 0.5)
                    ocr_confidence = ocr_data.get("ocr_confidence", 0.5)
                    ai_data["combined_confidence"] = (ai_confidence + ocr_confidence) / 2
                
                return ai_result
        
        # AIが失敗した場合はOCRのみ
        return self.ocr_processor.process_receipt_text(ocr_text)
    
    def _validate_image(self, image_bytes: bytes) -> bool:
        """画像の検証"""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            # フォーマットチェック
            allowed_formats = ['JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF', 'GIF']
            if image.format and image.format not in allowed_formats:
                logger.warning(f"Unsupported image format: {image.format}")
                return False
            
            # サイズチェック
            if len(image_bytes) > 50 * 1024 * 1024:
                return False
            
            # 寸法チェック
            width, height = image.size
            if width > 5000 or height > 5000:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Image validation error: {e}")
            return False
    
    def _suggest_category(self, data: Dict[str, Any]) -> Optional[str]:
        """店名や商品情報から費目カテゴリーを提案"""
        store_name = data.get("store_name", "").lower()
        
        # カテゴリー判定ルール
        categories = {
            "食費": ["スーパー", "コンビニ", "ファミリーマート", "セブンイレブン", "ローソン", 
                   "イオン", "マルエツ", "レストラン", "食堂", "カフェ"],
            "交通費": ["jr", "駅", "バス", "タクシー", "suica", "pasmo", "交通"],
            "日用品": ["ドラッグストア", "薬局", "ダイソー", "100均", "ホームセンター"],
            "書籍": ["書店", "本屋", "ブックオフ", "紀伊國屋"],
            "娯楽費": ["映画", "カラオケ", "ゲーム", "アミューズメント"],
            "医療費": ["病院", "クリニック", "薬局", "調剤"],
            "光熱費": ["電気", "ガス", "水道", "電力", "東京電力", "東京ガス"],
            "通信費": ["ドコモ", "au", "ソフトバンク", "携帯", "インターネット"],
        }
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in store_name:
                    return category
        
        return None
    
    def get_processing_capabilities(self) -> Dict[str, Any]:
        """現在の処理能力を返す"""
        available_modes = self._get_available_modes()
        
        return {
            "processing_mode": self.processing_mode,
            "capabilities": {
                "ocr": self.tesseract_available,
                "ai": self.openai_available,
                "vision": bool(self.openai_client),
                "advanced_image_processing": self.cv2_available,
                "heic_support": self.heif_available
            },
            "available_modes": available_modes,
            "recommended_mode": self._get_recommended_mode(available_modes)
        }
    
    def _get_available_modes(self) -> list:
        """利用可能な処理モードのリスト"""
        modes = []
        if self.tesseract_available:
            modes.append("ocr")
        if self.openai_available:
            modes.append("ai")
            if self.tesseract_available:
                modes.append("ai-ocr-hybrid")
        if self.openai_client:
            modes.append("vision")
        return modes
    
    def _get_recommended_mode(self, available_modes: list) -> str:
        """推奨される処理モード"""
        if "vision" in available_modes:
            return "vision"
        elif "ai-ocr-hybrid" in available_modes:
            return "ai-ocr-hybrid"
        elif "ai" in available_modes:
            return "ai"
        elif "ocr" in available_modes:
            return "ocr"
        return "unavailable"
