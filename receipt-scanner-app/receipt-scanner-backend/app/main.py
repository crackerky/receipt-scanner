from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import psycopg
import os
import io
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from dotenv import load_dotenv

from app.models import ReceiptData, ReceiptResponse, ReceiptList
from app.receipt_processor import ReceiptProcessor

load_dotenv()

app = FastAPI(title="Receipt Scanner API")

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

receipt_processor = ReceiptProcessor()

receipts_db: List[Dict[str, Any]] = []

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.post("/api/receipts/upload", response_model=ReceiptResponse)
async def upload_receipt(file: UploadFile = File(...)):
    """Upload and process a receipt image."""
    allowed_extensions = [".jpg", ".jpeg", ".png"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "サポートされていないファイル形式です。JPGまたはPNG形式のファイルをアップロードしてください。",
                "data": None
            }
        )
    
    try:
        contents = await file.read()
        
        result = receipt_processor.process_image(contents)
        
        if result["success"]:
            receipt_data = result["data"]
            receipt_data["id"] = len(receipts_db) + 1
            receipts_db.append(receipt_data)
        
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"画像処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
        )

@app.post("/api/receipts/test", response_model=ReceiptResponse)
async def test_receipt_upload():
    """Test endpoint for receipt upload without OCR."""
    try:
        receipt_data = {
            "date": "2023-05-15",
            "store_name": "テストストア",
            "total_amount": 1500.0,
            "tax_excluded_amount": 1364.0,
            "tax_included_amount": None,
            "expense_category": None
        }
        
        receipt_data["id"] = len(receipts_db) + 1
        receipts_db.append(receipt_data)
        
        return {
            "success": True,
            "message": "レシート情報を抽出しました。",
            "data": receipt_data
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
        )

@app.get("/api/receipts", response_model=ReceiptList)
async def get_receipts():
    """Get all receipts."""
    return {"receipts": receipts_db}

@app.get("/api/receipts/export")
async def export_receipts():
    """Export receipts as CSV."""
    if not receipts_db:
        return JSONResponse(
            status_code=404,
            content={"message": "エクスポートするデータがありません。"}
        )
    
    output = io.StringIO()
    fieldnames = ["date", "store_name", "total_amount", "tax_excluded_amount", "tax_included_amount", "expense_category"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    
    writer.writerow({
        "date": "日付",
        "store_name": "店名・会社名",
        "total_amount": "合計金額",
        "tax_excluded_amount": "税抜価格",
        "tax_included_amount": "税込価格",
        "expense_category": "費目タグ"
    })
    
    for receipt in receipts_db:
        writer.writerow({
            "date": receipt["date"],
            "store_name": receipt["store_name"],
            "total_amount": receipt["total_amount"],
            "tax_excluded_amount": receipt["tax_excluded_amount"] if receipt["tax_excluded_amount"] is not None else "",
            "tax_included_amount": receipt["tax_included_amount"] if receipt["tax_included_amount"] is not None else "",
            "expense_category": receipt["expense_category"] if receipt["expense_category"] is not None else ""
        })
    
    csv_content = output.getvalue()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    headers = {
        "Content-Disposition": f"attachment; filename=receipt_data_{timestamp}.csv",
        "Content-Type": "text/csv; charset=utf-8-sig",  # UTF-8 with BOM for Excel compatibility
        "Access-Control-Allow-Origin": "*",  # Add CORS header
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    }
    
    return JSONResponse(
        content={"csv_data": csv_content},
        headers=headers
    )

@app.delete("/api/receipts")
async def clear_receipts():
    """Clear all receipts from memory."""
    global receipts_db
    receipts_db = []
    return {"message": "すべてのレシートデータを削除しました。"}
