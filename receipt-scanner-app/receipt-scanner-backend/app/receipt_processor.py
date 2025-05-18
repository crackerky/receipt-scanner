import os
import io
import re
from datetime import datetime
from PIL import Image
import pytesseract
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import Dict, Any, Optional, Tuple

DATE_PATTERNS = [
    r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})',  # YYYY/MM/DD or YYYY-MM-DD or YYYY年MM月DD
    r'(\d{2})[/\-年](\d{1,2})[/\-月](\d{1,2})',   # YY/MM/DD or YY-MM-DD or YY年MM月DD
    r'令和(\d{1,2})年(\d{1,2})月(\d{1,2})日',    # Reiwa era
    r'平成(\d{1,2})年(\d{1,2})月(\d{1,2})日',    # Heisei era
]

AMOUNT_PATTERNS = [
    r'合計\s*[：:]\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'合計\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'(小計|総額|金額)\s*[：:]\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'(小計|総額|金額)\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
]

TAX_PATTERNS = [
    r'(税抜|税別)\s*[：:]\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'(税抜|税別)\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'(税込)\s*[：:]\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
    r'(税込)\s*¥?(\d{1,3}(,\d{3})*(\.\d+)?)',
]

class ReceiptProcessor:
    def __init__(self):
        self.openai_available = False
        if os.environ.get("OPENAI_API_KEY"):
            self.openai_available = True
            self.llm = ChatOpenAI(temperature=0)
            self.prompt = ChatPromptTemplate.from_template(
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
    
    def process_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Process receipt image and extract information."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            text = pytesseract.image_to_string(image, lang='jpn+eng')
            
            if self.openai_available:
                return self._extract_with_ai(text)
            else:
                return self._extract_with_regex(text)
        except Exception as e:
            return {
                "success": False,
                "message": f"画像処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
    
    def _extract_with_regex(self, text: str) -> Dict[str, Any]:
        """Extract receipt information using regex patterns."""
        date_str = self._extract_date(text)
        store_name = self._extract_store_name(text)
        total_amount = self._extract_amount(text)
        tax_excluded, tax_included = self._extract_tax_amounts(text)
        
        if not date_str or not store_name or not total_amount:
            missing = []
            if not date_str:
                missing.append("日付")
            if not store_name:
                missing.append("店名")
            if not total_amount:
                missing.append("合計金額")
            
            return {
                "success": False,
                "message": f"必要な情報（{', '.join(missing)}）を抽出できませんでした。画像の品質を確認し、再度お試しください。",
                "data": None
            }
        
        return {
            "success": True,
            "message": "レシート情報を抽出しました。",
            "data": {
                "date": date_str,
                "store_name": store_name,
                "total_amount": total_amount,
                "tax_excluded_amount": tax_excluded,
                "tax_included_amount": tax_included,
                "expense_category": None  # Will be set by frontend
            }
        }
    
    def _extract_with_ai(self, text: str) -> Dict[str, Any]:
        """Extract receipt information using AI."""
        try:
            response = self.llm.invoke(self.prompt.format(text=text))
            result = response.content
            
            import json
            import re
            
            json_match = re.search(r'{.*}', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                if not data.get("date") or not data.get("store_name") or not data.get("total_amount"):
                    missing = []
                    if not data.get("date"):
                        missing.append("日付")
                    if not data.get("store_name"):
                        missing.append("店名")
                    if not data.get("total_amount"):
                        missing.append("合計金額")
                    
                    return {
                        "success": False,
                        "message": f"必要な情報（{', '.join(missing)}）を抽出できませんでした。画像の品質を確認し、再度お試しください。",
                        "data": None
                    }
                
                return {
                    "success": True,
                    "message": "レシート情報を抽出しました。",
                    "data": {
                        "date": data.get("date"),
                        "store_name": data.get("store_name"),
                        "total_amount": float(data.get("total_amount")),
                        "tax_excluded_amount": float(data.get("tax_excluded_amount")) if data.get("tax_excluded_amount") else None,
                        "tax_included_amount": float(data.get("tax_included_amount")) if data.get("tax_included_amount") else None,
                        "expense_category": None  # Will be set by frontend
                    }
                }
            else:
                return self._extract_with_regex(text)
                
        except Exception as e:
            return self._extract_with_regex(text)
    
    def _extract_date(self, text: str) -> Optional[str]:
        """Extract date from receipt text."""
        for pattern in DATE_PATTERNS:
            matches = re.search(pattern, text)
            if matches:
                if "令和" in pattern:
                    year = 2018 + int(matches.group(1))
                    month = int(matches.group(2))
                    day = int(matches.group(3))
                elif "平成" in pattern:
                    year = 1988 + int(matches.group(1))
                    month = int(matches.group(2))
                    day = int(matches.group(3))
                else:
                    year = int(matches.group(1))
                    month = int(matches.group(2))
                    day = int(matches.group(3))
                    
                    if year < 100:
                        year += 2000 if year < 50 else 1900
                
                try:
                    date_obj = datetime(year, month, day)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        
        return None
    
    def _extract_store_name(self, text: str) -> Optional[str]:
        """Extract store name from receipt text."""
        lines = text.split('\n')
        for i in range(min(5, len(lines))):
            line = lines[i].strip()
            if line and len(line) > 1 and not any(char.isdigit() for char in line):
                return line
        
        for line in lines:
            if line.strip():
                return line.strip()
        
        return None
    
    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract total amount from receipt text."""
        for pattern in AMOUNT_PATTERNS:
            matches = re.search(pattern, text)
            if matches:
                amount_str = matches.group(1) if "合計" in pattern else matches.group(2)
                amount_str = amount_str.replace(',', '')
                try:
                    return float(amount_str)
                except ValueError:
                    continue
        
        return None
    
    def _extract_tax_amounts(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract tax excluded and included amounts from receipt text."""
        tax_excluded = None
        tax_included = None
        
        for pattern in TAX_PATTERNS:
            matches = re.search(pattern, text)
            if matches:
                tax_type = matches.group(1)
                amount_str = matches.group(2) if "税抜" in pattern or "税別" in pattern or "税込" in pattern else matches.group(2)
                amount_str = amount_str.replace(',', '')
                try:
                    amount = float(amount_str)
                    if "税抜" in tax_type or "税別" in tax_type:
                        tax_excluded = amount
                    elif "税込" in tax_type:
                        tax_included = amount
                except ValueError:
                    continue
        
        return tax_excluded, tax_included
