"""
AI（OpenAI）を使用したレシート処理モジュール
"""

import re
import json
import logging
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReceiptInfo(BaseModel):
    """レシート情報のスキーマ"""
    date: Optional[str] = Field(None, description="日付（YYYY-MM-DD形式）")
    store_name: str = Field(..., description="店名または会社名")
    total_amount: Optional[float] = Field(None, description="合計金額")
    tax_excluded_amount: Optional[float] = Field(None, description="税抜き価格")
    tax_included_amount: Optional[float] = Field(None, description="税込み価格")
    items: Optional[list] = Field(None, description="商品リスト")
    payment_method: Optional[str] = Field(None, description="支払い方法")
    receipt_number: Optional[str] = Field(None, description="レシート番号")


class AIProcessor:
    """AI（OpenAI）を使用したレシート処理クラス"""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        """
        Args:
            api_key: OpenAI APIキー
            model: 使用するモデル名
        """
        self.api_key = api_key
        self.model = model
        self.llm = None
        self.parser = PydanticOutputParser(pydantic_object=ReceiptInfo)
        self._initialize_llm()
    
    def _initialize_llm(self):
        """LLMの初期化"""
        try:
            self.llm = ChatOpenAI(
                api_key=self.api_key,
                model=self.model,
                temperature=0,
                max_retries=3,
                request_timeout=30.0
            )
            logger.info(f"AI processor initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize AI processor: {e}")
            self.llm = None
    
    def create_prompt_template(self) -> ChatPromptTemplate:
        """プロンプトテンプレートの作成"""
        format_instructions = self.parser.get_format_instructions()
        
        prompt = ChatPromptTemplate.from_template(
            """あなたは日本のレシート情報を正確に抽出する専門家です。
            
以下のレシートテキストから情報を抽出してください。

抽出ルール：
1. 日付は必ずYYYY-MM-DD形式に変換してください
2. 金額は数値のみ（カンマや円記号は除く）
3. 店名は正確に抽出してください
4. 商品情報があれば、商品名と価格のリストとして抽出
5. 支払い方法（現金、クレジット、電子マネーなど）も抽出
6. レシート番号があれば抽出

{format_instructions}

レシートテキスト:
{text}

注意事項：
- 情報が見つからない場合は null を設定
- 日付が部分的（月日のみ）の場合は、現在の年を補完
- 金額は最も大きい値が合計金額の可能性が高い
"""
        )
        
        return prompt.partial(format_instructions=format_instructions)
    
    def process_text(self, text: str) -> Dict[str, Any]:
        """AIを使用してテキストからレシート情報を抽出"""
        if not self.llm:
            return {
                "success": False,
                "message": "AI処理が利用できません。",
                "data": None
            }
        
        if not text.strip():
            return {
                "success": False,
                "message": "処理するテキストが空です。",
                "data": None
            }
        
        try:
            # プロンプトの作成
            prompt = self.create_prompt_template()
            
            # LLMの実行
            response = self.llm.invoke(prompt.format(text=text))
            
            # レスポンスのパース
            receipt_info = self._parse_response(response.content)
            
            if not receipt_info:
                return {
                    "success": False,
                    "message": "AI処理でレシート情報を抽出できませんでした。",
                    "data": None
                }
            
            # データの検証と整形
            processed_data = self._validate_and_format_data(receipt_info)
            
            return {
                "success": True,
                "message": "AI処理でレシート情報を抽出しました。",
                "data": processed_data,
                "ai_model": self.model
            }
            
        except Exception as e:
            logger.error(f"AI processing error: {e}")
            return {
                "success": False,
                "message": f"AI処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
    
    def _parse_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """AIレスポンスをパース"""
        try:
            # Pydanticパーサーを使用
            receipt_info = self.parser.parse(response_text)
            return receipt_info.dict()
        except Exception as e:
            logger.warning(f"Pydantic parsing failed: {e}")
            
            # フォールバック: JSON抽出を試みる
            try:
                json_match = re.search(r'{.*}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
            except Exception as e2:
                logger.error(f"JSON extraction also failed: {e2}")
                
        return None
    
    def _validate_and_format_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """データの検証と整形"""
        # 店名の検証
        if not data.get("store_name"):
            raise ValueError("店名が抽出されませんでした")
        
        # 日付の検証とフォーマット
        if data.get("date"):
            data["date"] = self._format_date(data["date"])
        
        # 金額の検証
        for amount_field in ["total_amount", "tax_excluded_amount", "tax_included_amount"]:
            if data.get(amount_field) is not None:
                try:
                    data[amount_field] = float(data[amount_field])
                except (ValueError, TypeError):
                    data[amount_field] = None
        
        # 商品リストの整形
        if data.get("items") and isinstance(data["items"], list):
            formatted_items = []
            for item in data["items"]:
                if isinstance(item, dict) and "name" in item:
                    formatted_item = {
                        "name": str(item.get("name", "")),
                        "price": float(item.get("price", 0)) if item.get("price") else None,
                        "quantity": int(item.get("quantity", 1)) if item.get("quantity") else 1
                    }
                    formatted_items.append(formatted_item)
            data["items"] = formatted_items if formatted_items else None
        
        # 追加フィールドの設定
        data["expense_category"] = self._suggest_category(data)
        data["ai_confidence"] = self._calculate_confidence(data)
        
        return data
    
    def _format_date(self, date_str: str) -> Optional[str]:
        """日付文字列をYYYY-MM-DD形式にフォーマット"""
        if not date_str:
            return None
        
        # 既に正しい形式の場合
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # その他の形式を変換
        import dateutil.parser
        try:
            date_obj = dateutil.parser.parse(date_str)
            return date_obj.strftime("%Y-%m-%d")
        except:
            logger.warning(f"Could not parse date: {date_str}")
            return None
    
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
        
        # 商品情報からも判断
        if data.get("items"):
            item_names = " ".join([item.get("name", "") for item in data["items"]]).lower()
            for category, keywords in categories.items():
                for keyword in keywords:
                    if keyword in item_names:
                        return category
        
        return None
    
    def _calculate_confidence(self, data: Dict[str, Any]) -> float:
        """AI抽出結果の信頼度を計算"""
        confidence = 0.0
        
        # 必須項目の存在チェック
        if data.get("store_name"):
            confidence += 0.3
        if data.get("total_amount") is not None:
            confidence += 0.3
        if data.get("date"):
            confidence += 0.2
        
        # 追加情報の存在チェック
        if data.get("items"):
            confidence += 0.1
        if data.get("payment_method"):
            confidence += 0.05
        if data.get("receipt_number"):
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    def extract_with_context(self, text: str, image_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """コンテキスト情報を使用した抽出（拡張版）"""
        # 画像メタデータから追加情報を取得
        context = ""
        if image_metadata:
            if image_metadata.get("location"):
                context += f"\n場所情報: {image_metadata['location']}"
            if image_metadata.get("timestamp"):
                context += f"\n撮影日時: {image_metadata['timestamp']}"
        
        # コンテキストを含めたテキスト
        enhanced_text = text + context
        
        # 通常の処理を実行
        result = self.process_text(enhanced_text)
        
        # メタデータから日付を補完
        if result["success"] and result["data"] and not result["data"].get("date"):
            if image_metadata and image_metadata.get("timestamp"):
                result["data"]["date"] = image_metadata["timestamp"].split("T")[0]
                result["message"] += " （撮影日時から日付を補完）"
        
        return result
