import logging
import time
from functools import wraps
from typing import Dict, Any, List
import io
import csv
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
import psycopg

from app.config import settings
from app.models import ReceiptData, ReceiptResponse, ReceiptList
from app.receipt_processor import ReceiptProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Receipt Scanner API",
    description="Secure receipt scanning and processing API",
    version="1.0.0",
    debug=settings.debug
)

# 開発環境用の追加CORS設定
development_origins = [
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://localhost:3000",
    "https://localhost:5173",
]

# Configure CORS with secure settings
allowed_origins = settings.allowed_origins.copy()
if settings.is_development:
    allowed_origins.extend(development_origins)

# 重複を削除
allowed_origins = list(set(allowed_origins))

logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize components
receipt_processor = ReceiptProcessor()
security = HTTPBearer(auto_error=False)

# In-memory storage (replace with database in production)
receipts_db: List[Dict[str, Any]] = []

# Rate limiting storage
rate_limit_storage: Dict[str, List[float]] = {}

def rate_limit(max_requests: int = None, window: int = None):
    """Rate limiting decorator."""
    max_req = max_requests or settings.rate_limit_requests
    window_sec = window or settings.rate_limit_window
    
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_ip = request.client.host
            current_time = time.time()
            
            # Initialize storage for IP if not exists
            if client_ip not in rate_limit_storage:
                rate_limit_storage[client_ip] = []
            
            # Clean old requests
            rate_limit_storage[client_ip] = [
                req_time for req_time in rate_limit_storage[client_ip]
                if current_time - req_time < window_sec
            ]
            
            # Check rate limit
            if len(rate_limit_storage[client_ip]) >= max_req:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {max_req} requests per {window_sec} seconds."
                )
            
            # Record current request
            rate_limit_storage[client_ip].append(current_time)
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests for debugging."""
    start_time = time.time()
    
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} - {process_time:.3f}s")
    
    return response

@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "openai_available": settings.openai_available,
        "cors_origins": allowed_origins[:3] if len(allowed_origins) > 3 else allowed_origins,  # セキュリティのため一部のみ表示
    }

@app.get("/api/status")
async def api_status():
    """API status endpoint with service information."""
    return {
        "api_version": "1.0.0",
        "environment": settings.environment,
        "features": {
            "openai_processing": settings.openai_available,
            "ocr_fallback": True,
            "rate_limiting": True,
            "heic_support": receipt_processor.heif_available
        },
        "limits": {
            "max_requests_per_minute": settings.rate_limit_requests,
            "max_file_size_mb": 50
        },
        "cors_enabled": True,
        "allowed_origins_count": len(allowed_origins),
        "supported_formats": [".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tiff", ".tif"]
    }

@app.post("/api/receipts/upload", response_model=ReceiptResponse)
@rate_limit()
async def upload_receipt(request: Request, file: UploadFile = File(...)):
    """Upload and process a receipt image with security validation."""
    
    logger.info(f"Upload request from: {request.client.host}")
    logger.info(f"File info: name={file.filename}, content_type={file.content_type}, size={file.size if hasattr(file, 'size') else 'unknown'}")
    
    # Validate file
    if not file.filename:
        logger.warning("No filename provided")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "ファイル名が提供されていません。",
                "data": None
            }
        )
    
    # ファイル拡張子を取得（大文字小文字を無視）
    file_ext = ""
    if "." in file.filename:
        file_ext = file.filename.split(".")[-1].lower()
    
    logger.info(f"File extension detected: {file_ext}")
    
    # より寛容なファイル形式チェック
    # 拡張子がない場合でも、content-typeで判定
    allowed_extensions = ["jpg", "jpeg", "png", "heic", "heif", "webp", "bmp", "tiff", "tif", "gif"]
    allowed_content_types = [
        "image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif", 
        "image/webp", "image/bmp", "image/tiff", "image/gif", "application/octet-stream",
        "image/*"  # ワイルドカードも許可
    ]
    
    # content-typeのチェック（ワイルドカード対応）
    content_type_valid = any(
        file.content_type == ct or 
        (ct.endswith("/*") and file.content_type and file.content_type.startswith(ct[:-2]))
        for ct in allowed_content_types
    )
    
    # 拡張子とcontent-typeの両方をチェック
    if file_ext and file_ext not in allowed_extensions and not content_type_valid:
        logger.warning(f"Unsupported file - extension: {file_ext}, content_type: {file.content_type}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"画像ファイルとして認識できません。一般的な画像形式（JPEG, PNG, HEIC, WebP等）のファイルをアップロードしてください。",
                "data": None,
                "debug_info": {
                    "detected_extension": file_ext,
                    "content_type": file.content_type,
                    "filename": file.filename
                } if settings.debug else None
            }
        )
    
    # Check file size (50MB limit for mobile photos)
    content = await file.read()
    logger.info(f"File content size: {len(content)} bytes")
    
    if len(content) > 50 * 1024 * 1024:
        logger.warning(f"File too large: {len(content)} bytes")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "ファイルサイズが大きすぎます。50MB以下のファイルをアップロードしてください。",
                "data": None
            }
        )
    
    # ファイルが空でないかチェック
    if len(content) == 0:
        logger.warning("Empty file uploaded")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "空のファイルがアップロードされました。有効な画像ファイルを選択してください。",
                "data": None
            }
        )
    
    try:
        # Process the image
        logger.info("Starting image processing...")
        result = receipt_processor.process_image(content)
        logger.info(f"Processing result: {result['success']}")
        
        if result["success"]:
            # Add unique ID and timestamp
            receipt_data = result["data"]
            receipt_data["id"] = len(receipts_db) + 1
            receipt_data["created_at"] = datetime.utcnow().isoformat()
            receipt_data["processed_with"] = "ai" if settings.openai_available else "ocr"
            
            # Store in database
            receipts_db.append(receipt_data)
            
            logger.info(f"Successfully processed receipt {receipt_data['id']}")
        else:
            logger.warning(f"Processing failed: {result['message']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing receipt: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "画像処理中にサーバーエラーが発生しました。しばらく時間をおいて再度お試しください。",
                "data": None,
                "error_details": str(e) if settings.debug else None
            }
        )

@app.post("/api/receipts/file-info")
async def file_info(file: UploadFile = File(...)):
    """ファイル情報を確認するデバッグエンドポイント"""
    content = await file.read()
    
    # ファイルヘッダーから形式を推測
    file_header = content[:12] if len(content) >= 12 else content
    detected_format = "unknown"
    
    if file_header[:3] == b'\xff\xd8\xff':
        detected_format = "JPEG"
    elif file_header[:8] == b'\x89PNG\r\n\x1a\n':
        detected_format = "PNG"
    elif file_header[4:8] == b'ftyp':
        detected_format = "HEIC/HEIF"
    elif file_header[:4] == b'RIFF' and file_header[8:12] == b'WEBP':
        detected_format = "WebP"
    elif file_header[:2] == b'BM':
        detected_format = "BMP"
    elif file_header[:2] == b'II' or file_header[:2] == b'MM':
        detected_format = "TIFF"
    
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "file_size": len(content),
        "detected_extension": file.filename.split(".")[-1].lower() if "." in file.filename else "none",
        "detected_format": detected_format,
        "file_header_hex": file_header.hex(),
        "supported": True  # 基本的にすべてサポート
    }

@app.post("/api/receipts/debug", response_model=Dict[str, Any])
@rate_limit()
async def debug_receipt(request: Request, file: UploadFile = File(...)):
    """Debug endpoint to see OCR output without processing."""
    
    logger.info(f"Debug request from: {request.client.host}")
    
    # Check file
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "ファイル名が提供されていません。",
                "ocr_text": None
            }
        )
    
    # Read file
    content = await file.read()
    
    # ファイル情報をログ
    logger.info(f"Debug - filename: {file.filename}, content_type: {file.content_type}, size: {len(content)}")
    
    try:
        from PIL import Image
        import pytesseract
        
        # HEIC変換を試みる
        if len(content) >= 12 and content[4:8] == b'ftyp':
            logger.info("Debug - HEIC format detected, attempting conversion")
            from app.receipt_processor import ReceiptProcessor
            processor = ReceiptProcessor()
            content = processor._convert_heic_to_jpeg(content)
        
        # Open and preprocess image
        image = Image.open(io.BytesIO(content))
        logger.info(f"Debug - Image opened successfully: size={image.size}, mode={image.mode}")
        
        # Basic preprocessing
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image = image.convert('L')  # Grayscale
        
        # Run OCR
        ocr_text = pytesseract.image_to_string(image, lang='jpn+eng')
        
        # Also try to extract with regex patterns
        from app.receipt_processor import DATE_PATTERNS, AMOUNT_PATTERNS
        import re
        
        dates_found = []
        amounts_found = []
        
        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, ocr_text)
            if matches:
                dates_found.extend(matches)
        
        for pattern in AMOUNT_PATTERNS:
            matches = re.findall(pattern, ocr_text)
            if matches:
                amounts_found.extend(matches)
        
        return {
            "success": True,
            "message": "OCRデバッグ結果",
            "ocr_text": ocr_text,
            "ocr_text_length": len(ocr_text),
            "dates_found": dates_found,
            "amounts_found": amounts_found,
            "openai_available": settings.openai_available,
            "tesseract_available": receipt_processor.tesseract_available,
            "cv2_available": receipt_processor.cv2_available,
            "heif_available": receipt_processor.heif_available,
            "file_info": {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content)
            }
        }
        
    except Exception as e:
        logger.error(f"Debug processing error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"デバッグ処理中にエラーが発生しました: {str(e)}",
                "ocr_text": None,
                "error_type": type(e).__name__
            }
        )

@app.post("/api/receipts/test", response_model=ReceiptResponse)
async def test_receipt_upload():
    """Test endpoint for receipt upload without file processing."""
    try:
        receipt_data = {
            "id": len(receipts_db) + 1,
            "date": "2023-05-15",
            "store_name": "テストストア",
            "total_amount": 1500.0,
            "tax_excluded_amount": 1364.0,
            "tax_included_amount": None,
            "expense_category": None,
            "created_at": datetime.utcnow().isoformat(),
            "processed_with": "test"
        }
        
        receipts_db.append(receipt_data)
        
        logger.info(f"Created test receipt {receipt_data['id']}")
        
        return {
            "success": True,
            "message": "テストレシート情報を作成しました。",
            "data": receipt_data
        }
        
    except Exception as e:
        logger.error(f"Error in test endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"テスト処理中にエラーが発生しました: {str(e)}",
                "data": None
            }
        )

@app.get("/api/receipts", response_model=ReceiptList)
async def get_receipts():
    """Get all receipts with pagination support."""
    try:
        # Sort by creation date (newest first)
        sorted_receipts = sorted(
            receipts_db, 
            key=lambda x: x.get("created_at", ""), 
            reverse=True
        )
        
        logger.info(f"Retrieved {len(sorted_receipts)} receipts")
        
        return {"receipts": sorted_receipts}
        
    except Exception as e:
        logger.error(f"Error retrieving receipts: {e}")
        raise HTTPException(status_code=500, detail="レシート一覧の取得中にエラーが発生しました。")

@app.get("/api/receipts/{receipt_id}")
async def get_receipt(receipt_id: int):
    """Get a specific receipt by ID."""
    try:
        receipt = next((r for r in receipts_db if r["id"] == receipt_id), None)
        if not receipt:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        return {"receipt": receipt}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="レシート取得中にエラーが発生しました。")

@app.put("/api/receipts/{receipt_id}")
async def update_receipt(receipt_id: int, receipt_data: ReceiptData):
    """Update a specific receipt."""
    try:
        receipt_index = next((i for i, r in enumerate(receipts_db) if r["id"] == receipt_id), None)
        if receipt_index is None:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        # Update receipt data
        updated_receipt = receipt_data.dict()
        updated_receipt["id"] = receipt_id
        updated_receipt["updated_at"] = datetime.utcnow().isoformat()
        
        receipts_db[receipt_index].update(updated_receipt)
        
        return {
            "success": True,
            "message": "レシート情報を更新しました。",
            "data": receipts_db[receipt_index]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="レシート更新中にエラーが発生しました。")

@app.delete("/api/receipts/{receipt_id}")
async def delete_receipt(receipt_id: int):
    """Delete a specific receipt."""
    try:
        receipt_index = next((i for i, r in enumerate(receipts_db) if r["id"] == receipt_id), None)
        if receipt_index is None:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        deleted_receipt = receipts_db.pop(receipt_index)
        
        return {
            "success": True,
            "message": "レシートを削除しました。",
            "data": {"deleted_id": receipt_id}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="レシート削除中にエラーが発生しました。")

@app.get("/api/receipts/export")
async def export_receipts():
    """Export receipts as CSV with secure filename generation."""
    try:
        if not receipts_db:
            return JSONResponse(
                status_code=404,
                content={"message": "エクスポートするデータがありません。"}
            )
        
        # Create CSV content
        output = io.StringIO()
        fieldnames = [
            "id", "date", "store_name", "total_amount", 
            "tax_excluded_amount", "tax_included_amount", 
            "expense_category", "created_at", "processed_with"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        # Write header in Japanese
        writer.writerow({
            "id": "ID",
            "date": "日付",
            "store_name": "店名・会社名",
            "total_amount": "合計金額",
            "tax_excluded_amount": "税抜価格",
            "tax_included_amount": "税込価格",
            "expense_category": "費目タグ",
            "created_at": "作成日時",
            "processed_with": "処理方法"
        })
        
        # Write data rows
        for receipt in sorted(receipts_db, key=lambda x: x.get("created_at", "")):
            writer.writerow({
                "id": receipt.get("id", ""),
                "date": receipt.get("date", ""),
                "store_name": receipt.get("store_name", ""),
                "total_amount": receipt.get("total_amount", ""),
                "tax_excluded_amount": receipt.get("tax_excluded_amount", "") if receipt.get("tax_excluded_amount") is not None else "",
                "tax_included_amount": receipt.get("tax_included_amount", "") if receipt.get("tax_included_amount") is not None else "",
                "expense_category": receipt.get("expense_category", "") if receipt.get("expense_category") is not None else "",
                "created_at": receipt.get("created_at", ""),
                "processed_with": receipt.get("processed_with", "")
            })
        
        csv_content = output.getvalue()
        
        # Generate secure filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"receipt_data_{timestamp}.csv"
        
        headers = {
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8-sig",  # UTF-8 with BOM for Excel compatibility
        }
        
        return JSONResponse(
            content={"csv_data": csv_content, "filename": filename},
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Error exporting receipts: {e}")
        raise HTTPException(status_code=500, detail="データエクスポート中にエラーが発生しました。")

@app.delete("/api/receipts")
async def clear_receipts():
    """Clear all receipts from memory (development only)."""
    try:
        if settings.is_production:
            raise HTTPException(
                status_code=403, 
                detail="本番環境では全データ削除は許可されていません。"
            )
        
        global receipts_db
        count = len(receipts_db)
        receipts_db = []
        
        logger.info(f"Cleared {count} receipts from memory")
        
        return {
            "success": True,
            "message": f"{count}件のレシートデータを削除しました。",
            "data": {"deleted_count": count}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing receipts: {e}")
        raise HTTPException(status_code=500, detail="データ削除中にエラーが発生しました。")

@app.get("/api/stats")
async def get_statistics():
    """Get receipt statistics."""
    try:
        if not receipts_db:
            return {
                "total_receipts": 0,
                "total_amount": 0,
                "average_amount": 0,
                "processing_methods": {}
            }
        
        total_receipts = len(receipts_db)
        total_amount = sum(r.get("total_amount", 0) for r in receipts_db)
        average_amount = total_amount / total_receipts if total_receipts > 0 else 0
        
        # Count processing methods
        processing_methods = {}
        for receipt in receipts_db:
            method = receipt.get("processed_with", "unknown")
            processing_methods[method] = processing_methods.get(method, 0) + 1
        
        return {
            "total_receipts": total_receipts,
            "total_amount": total_amount,
            "average_amount": round(average_amount, 2),
            "processing_methods": processing_methods
        }
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail="統計情報取得中にエラーが発生しました。")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler."""
    logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "data": None
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "予期しないエラーが発生しました。しばらく時間をおいて再度お試しください。",
            "data": None,
            "error_details": str(exc) if settings.debug else None
        }
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info(f"Receipt Scanner API starting up in {settings.environment} mode")
    logger.info(f"OpenAI API available: {settings.openai_available}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed origins: {allowed_origins}")
    logger.info(f"HEIF support available: {receipt_processor.heif_available}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Receipt Scanner API shutting down")
