"""
OCR専用の処理モジュール
AI-OCR機能と通常のOCR処理を分離して、より明確な構造にする
"""

import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract

logger = logging.getLogger(__name__)


class OCRProcessor:
    """OCR専用の処理クラス"""
    
    # 日付パターン（改良版）
    DATE_PATTERNS = [
        # YYYY/MM/DD, YYYY-MM-DD, YYYY年MM月DD日
        r'(\d{4})[/\-年][\s]*(\d{1,2})[/\-月][\s]*(\d{1,2})',
        # YY/MM/DD, YY-MM-DD, YY年MM月DD日
        r'(\d{2})[/\-年][\s]*(\d{1,2})[/\-月][\s]*(\d{1,2})',
        # 令和/平成
        r'令和[\s]*(\d{1,2})年[\s]*(\d{1,2})月[\s]*(\d{1,2})日',
        r'平成[\s]*(\d{1,2})年[\s]*(\d{1,2})月[\s]*(\d{1,2})日',
        # MM/DD形式（年なし）
        r'(\d{1,2})[/\-月][\s]*(\d{1,2})日?',
        # 2023.05.15形式
        r'(\d{4})\.[\s]*(\d{1,2})\.[\s]*(\d{1,2})',
        # 23.05.15形式
        r'(\d{2})\.[\s]*(\d{1,2})\.[\s]*(\d{1,2})',
        # スペースが含まれる場合
        r'(\d{4})\s+(\d{1,2})\s+(\d{1,2})',
        # 年月日が漢字で区切られている
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        r'(\d{2})年(\d{1,2})月(\d{1,2})日',
        # 日付っぽいパターン（より柔軟）
        r'(\d{4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})',
        r'(\d{2})[^\d]+(\d{1,2})[^\d]+(\d{1,2})',
    ]
    
    # 金額パターン（改良版）
    AMOUNT_PATTERNS = [
        # 合計パターン（様々なバリエーション）
        r'合\s*計\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'合計\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'計\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'お買上げ合計\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # 小計/総額/金額パターン
        r'(?:小計|総額|金額|お支払い金額)\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # ¥記号付きパターン（全角・半角対応）
        r'[¥￥]\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # 円付きパターン
        r'(\d{1,3}(?:[,，]\d{3})*)\s*円',
        
        # お預かり/お釣りパターン
        r'お預[かり]*\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'お釣[り]*\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # TOTAL（英語）パターン
        r'TOTAL\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'Total\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # 現計/現金パターン
        r'現[計金]\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        
        # 数字のみのパターン（改善版）
        r'[¥￥]\s*(\d{3,}(?:[,，]\d{3})*)',
        r'(\d{3,}(?:[,，]\d{3})*)\s*$',
        r'^\s*(\d{3,}(?:[,，]\d{3})*)',
        
        # スペースが含まれる数字
        r'(\d{1,3}(?:\s+\d{3})*)',
        
        # より柔軟なパターン
        r'(\d+[,，]?\d*)\s*円',
        r'[¥￥]\s*(\d+[,，]?\d*)',
    ]
    
    # 税額パターン
    TAX_PATTERNS = [
        r'(税抜|税別)\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'(税込)\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'内税\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'消費税\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'外税\s*[:：]?\s*[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
    ]
    
    # 商品パターン
    ITEM_PATTERNS = [
        # 商品名と価格のパターン
        r'([^\d\n]{2,})\s+[¥￥]?\s*(\d{1,3}(?:[,，]\d{3})*)',
        r'([^\d\n]{2,})\s+(\d{1,3}(?:[,，]\d{3})*)\s*円',
    ]
    
    def __init__(self, cv2_available: bool = True):
        self.cv2_available = cv2_available
        
    def preprocess_image(self, image: Image.Image, advanced: bool = True) -> Image.Image:
        """画像の前処理"""
        if advanced and self.cv2_available:
            return self._preprocess_advanced(image)
        else:
            return self._preprocess_basic(image)
    
    def _preprocess_advanced(self, image: Image.Image) -> Image.Image:
        """OpenCVを使用した高度な前処理"""
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
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = 90 + angle
                
                # 回転補正
                (h, w) = cleaned.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(cleaned, M, (w, h), 
                                       flags=cv2.INTER_CUBIC, 
                                       borderMode=cv2.BORDER_REPLICATE)
            else:
                rotated = cleaned
            
            # OpenCV画像をPIL Imageに変換
            result_image = Image.fromarray(rotated)
            
            logger.info("Advanced image preprocessing completed")
            return result_image
            
        except Exception as e:
            logger.warning(f"Advanced preprocessing failed: {e}")
            return self._preprocess_basic(image)
    
    def _preprocess_basic(self, image: Image.Image) -> Image.Image:
        """基本的な画像前処理"""
        # RGBに変換
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
        
        # リサイズ（大きすぎる場合）
        width, height = image.size
        if width > 2000 or height > 2000:
            ratio = min(2000/width, 2000/height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return image
    
    def extract_text(self, image: Image.Image, lang: str = 'jpn+eng') -> str:
        """OCRでテキストを抽出"""
        # Tesseractの設定を最適化
        custom_configs = [
            r'--oem 3 --psm 6',  # デフォルト設定
            r'--oem 1 --psm 3',  # LSTM only, 自動ページ分割
            r'--oem 3 --psm 4',  # 単一列のテキスト
            r'--oem 3 --psm 11', # スパーステキスト
        ]
        
        best_text = ""
        max_length = 0
        
        for config in custom_configs:
            try:
                text = pytesseract.image_to_string(image, lang=lang, config=config)
                if len(text) > max_length:
                    max_length = len(text)
                    best_text = text
                    logger.debug(f"Better OCR result with config: {config}, length: {len(text)}")
            except Exception as e:
                logger.warning(f"OCR failed with config {config}: {e}")
                continue
        
        return best_text
    
    def extract_date(self, text: str) -> Optional[str]:
        """テキストから日付を抽出"""
        current_year = datetime.now().year
        
        for pattern in self.DATE_PATTERNS:
            matches = re.search(pattern, text)
            if matches:
                try:
                    groups = matches.groups()
                    groups = [g.strip() if isinstance(g, str) else g for g in groups]
                    
                    if "令和" in pattern:
                        year = 2018 + int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                    elif "平成" in pattern:
                        year = 1988 + int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                    elif len(groups) == 2:  # MM/DD形式
                        year = current_year
                        month = int(groups[0])
                        day = int(groups[1])
                    else:
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                        
                        if year < 100:
                            year += 2000 if year < 50 else 1900
                    
                    # 妥当性チェック
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        date_obj = datetime(year, month, day)
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, IndexError) as e:
                    logger.debug(f"Date extraction failed for pattern {pattern}: {e}")
                    continue
        
        return None
    
    def extract_store_name(self, text: str) -> Optional[str]:
        """テキストから店名を抽出"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # 最初の数行から店名を探す
        for i in range(min(10, len(lines))):
            line = lines[i]
            if line and len(line) > 1 and len(line) < 50:
                # 数字の割合が30%未満の行を店名候補とする
                digit_count = sum(1 for char in line if char.isdigit())
                if len(line) > 0 and digit_count / len(line) < 0.3:
                    # OCRアーティファクトを除去
                    cleaned = re.sub(r'[^\w\s\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', line)
                    if cleaned and len(cleaned) > 1:
                        logger.debug(f"Store name candidate: {cleaned}")
                        return cleaned
        
        # フォールバック：最初の空でない行
        for line in lines:
            if line and len(line) > 1:
                return line[:50]
        
        return None
    
    def extract_amount(self, text: str) -> Optional[float]:
        """テキストから金額を抽出"""
        amounts_found = []
        
        # 全角数字を半角に変換
        normalized_text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        for pattern in self.AMOUNT_PATTERNS:
            matches = re.findall(pattern, normalized_text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        amount_str = match[0]
                    else:
                        amount_str = match
                    
                    # カンマ、全角カンマ、スペースを削除
                    amount_str = amount_str.replace(',', '').replace('，', '').replace(' ', '')
                    amount = float(amount_str)
                    
                    # 妥当な金額範囲かチェック（1円〜1000万円）
                    if 1 <= amount <= 10000000:
                        amounts_found.append((amount, pattern))
                        logger.debug(f"Amount found: {amount} (pattern: {pattern})")
                except (ValueError, IndexError):
                    continue
        
        # 最も妥当な金額を選択
        if amounts_found:
            # 「合計」パターンを優先
            for amount, pattern in amounts_found:
                if '合' in pattern or 'TOTAL' in pattern.upper():
                    return amount
            
            # それ以外は最大値を返す
            return max(amounts_found, key=lambda x: x[0])[0]
        
        return None
    
    def extract_tax_amounts(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """テキストから税額を抽出"""
        tax_excluded = None
        tax_included = None
        
        normalized_text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        for pattern in self.TAX_PATTERNS:
            matches = re.findall(pattern, normalized_text)
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
                    
                    amount_str = amount_str.replace(',', '').replace('，', '').replace(' ', '')
                    amount = float(amount_str)
                    
                    if "税抜" in tax_type or "税別" in tax_type:
                        tax_excluded = amount
                    elif "税込" in tax_type:
                        tax_included = amount
                except (ValueError, IndexError):
                    continue
        
        return tax_excluded, tax_included
    
    def extract_items(self, text: str) -> List[Dict[str, Any]]:
        """テキストから商品情報を抽出"""
        items = []
        normalized_text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        for pattern in self.ITEM_PATTERNS:
            matches = re.findall(pattern, normalized_text)
            for match in matches:
                try:
                    if isinstance(match, tuple) and len(match) >= 2:
                        item_name = match[0].strip()
                        price_str = match[1].replace(',', '').replace('，', '').replace(' ', '')
                        price = float(price_str)
                        
                        if len(item_name) > 1 and 1 <= price <= 100000:
                            items.append({
                                "name": item_name,
                                "price": price
                            })
                except (ValueError, IndexError):
                    continue
        
        return items
    
    def process_receipt_text(self, text: str) -> Dict[str, Any]:
        """OCRテキストから情報を抽出"""
        if not text.strip():
            return {
                "success": False,
                "message": "OCRでテキストを抽出できませんでした。",
                "data": None
            }
        
        # 各種情報を抽出
        date_str = self.extract_date(text)
        store_name = self.extract_store_name(text)
        total_amount = self.extract_amount(text)
        tax_excluded, tax_included = self.extract_tax_amounts(text)
        items = self.extract_items(text)
        
        # 抽出できなかった項目を記録
        missing_fields = []
        if not date_str:
            missing_fields.append("日付")
        if not store_name:
            missing_fields.append("店名")
        if not total_amount:
            missing_fields.append("合計金額")
        
        # 店名が取れなかった場合はエラー
        if not store_name:
            return {
                "success": False,
                "message": "店名を抽出できませんでした。画像の品質を確認してください。",
                "data": None
            }
        
        # 結果を返す
        return {
            "success": True,
            "message": f"OCR処理でレシート情報を抽出しました。{'（' + '、'.join(missing_fields) + 'は抽出できませんでした）' if missing_fields else ''}",
            "data": {
                "date": date_str,
                "store_name": store_name,
                "total_amount": total_amount,
                "tax_excluded_amount": tax_excluded,
                "tax_included_amount": tax_included,
                "items": items if items else None,
                "expense_category": None,
                "ocr_confidence": self._calculate_confidence(text, store_name, total_amount, date_str)
            }
        }
    
    def _calculate_confidence(self, text: str, store_name: Optional[str], 
                            amount: Optional[float], date: Optional[str]) -> float:
        """OCR結果の信頼度を計算"""
        confidence = 0.0
        
        # テキスト量による評価
        if len(text) > 100:
            confidence += 0.2
        if len(text) > 300:
            confidence += 0.1
        
        # 抽出項目による評価
        if store_name:
            confidence += 0.3
        if amount:
            confidence += 0.3
        if date:
            confidence += 0.1
        
        # テキストの品質評価（数字と文字のバランス）
        digit_ratio = sum(1 for c in text if c.isdigit()) / len(text) if text else 0
        if 0.1 < digit_ratio < 0.5:
            confidence += 0.1
        
        return min(confidence, 1.0)
