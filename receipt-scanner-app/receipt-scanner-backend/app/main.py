import logging
import time
from functools import wraps
from typing import Dict, Any, List, Optional
import io
import csv
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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
    description="Secure receipt scanning and processing API with AI-OCR hybrid support",
    version="2.0.0",
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
    logger.debug(f"Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} - {process_time:.3f}s")
    
    return response

@app.get("/")
async def root():
    """Root endpoint."""
    capabilities = receipt_processor.get_processing_capabilities()
    
    return {
        "message": "Receipt Scanner API",
        "version": "2.0.0",
        "status": "active",
        "processing_capabilities": capabilities,
        "endpoints": {
            "health": "/healthz",
            "api_status": "/api/status",
            "upload": "/api/receipts/upload",
            "receipts": "/api/receipts",
            "capabilities": "/api/capabilities"
        }
    }

@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "openai_available": settings.openai_available,
        "cors_origins": allowed_origins[:3] if len(allowed_origins) > 3 else allowed_origins,
    }

@app.get("/api/status")
async def api_status():
    """API status endpoint with service information."""
    capabilities = receipt_processor.get_processing_capabilities()
    
    return {
        "api_version": "2.0.0",
        "environment": settings.environment,
        "features": {
            "openai_processing": capabilities["capabilities"]["ai"],
            "ocr_processing": capabilities["capabilities"]["ocr"],
            "ai_ocr_hybrid": "ai-ocr-hybrid" in capabilities["available_modes"],
            "rate_limiting": True,
            "heic_support": capabilities["capabilities"]["heic_support"],
            "advanced_image_processing": capabilities["capabilities"]["advanced_image_processing"]
        },
        "processing_mode": capabilities["processing_mode"],
        "available_modes": capabilities["available_modes"],
        "limits": {
            "max_requests_per_minute": settings.rate_limit_requests,
            "max_file_size_mb": 50
        },
        "cors_enabled": True,
        "allowed_origins_count": len(allowed_origins),
        "supported_formats": [".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tiff", ".tif"]
    }

@app.get("/api/capabilities")
async def get_capabilities():
    """Get detailed processing capabilities."""
    return receipt_processor.get_processing_capabilities()

@app.post("/api/receipts/upload", response_model=ReceiptResponse)
@rate_limit()
async def upload_receipt(
    request: Request, 
    file: UploadFile = File(...),
    processing_mode: Optional[str] = Query(None, description="Processing mode: 'ai', 'ocr', or 'auto'")
):
    """
    Upload and process a receipt image.
    
    Processing modes:
    - 'ai': Use only AI processing (requires OpenAI API)
    - 'ocr': Use only OCR processing
    - 'auto' or None: Use AI-OCR hybrid mode (recommended)
    """
    
    logger.info(f"Upload request from: {request.client.host}")
    logger.info(f"Processing mode requested: {processing_mode}")
    logger.info(f"File info: name={file.filename}, content_type={file.content_type}")
    
    # Validate processing mode
    if processing_mode and processing_mode not in ["ai", "ocr", "auto"]:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "無効な処理モードです。'ai', 'ocr', または 'auto' を指定してください。",
                "data": None
            }
        )
    
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
    
    # ファイル拡張子を取得
    file_ext = ""
    if "." in file.filename:
        file_ext = file.filename.split(".")[-1].lower()
    
    logger.info(f"File extension detected: {file_ext}")
    
    # ファイル形式チェック
    allowed_extensions = ["jpg", "jpeg", "png", "heic", "heif", "webp", "bmp", "tiff", "tif", "gif"]
    allowed_content_types = [
        "image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif", 
        "image/webp", "image/bmp", "image/tiff", "image/gif", "application/octet-stream",
        "image/*"
    ]
    
    # content-typeのチェック
    content_type_valid = any(
        file.content_type == ct or 
        (ct.endswith("/*") and file.content_type and file.content_type.startswith(ct[:-2]))
        for ct in allowed_content_types
    )
    
    if file_ext and file_ext not in allowed_extensions and not content_type_valid:
        logger.warning(f"Unsupported file - extension: {file_ext}, content_type: {file.content_type}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "画像ファイルとして認識できません。対応している画像形式をアップロードしてください。",
                "data": None,
                "debug_info": {
                    "detected_extension": file_ext,
                    "content_type": file.content_type,
                    "filename": file.filename
                } if settings.debug else None
            }
        )
    
    # ファイルサイズチェック
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
    
    if len(content) == 0:
        logger.warning("Empty file uploaded")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "空のファイルがアップロードされました。",
                "data": None
            }
        )
    
    try:
        # Process the image
        logger.info("Starting image processing...")
        result = receipt_processor.process_image(content, processing_mode=processing_mode)
        logger.info(f"Processing result: {result['success']}")
        
        if result["success"]:
            # Add unique ID and timestamp
            receipt_data = result["data"]
            receipt_data["id"] = len(receipts_db) + 1
            receipt_data["created_at"] = datetime.utcnow().isoformat()
            
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
                "message": "画像処理中にサーバーエラーが発生しました。",
                "data": None,
                "error_details": str(e) if settings.debug else None
            }
        )

@app.post("/api/receipts/analyze", response_model=Dict[str, Any])
@rate_limit()
async def analyze_receipt(
    request: Request,
    file: UploadFile = File(...),
    detailed: bool = Query(False, description="Return detailed analysis")
):
    """
    Analyze receipt image and return detailed information without saving.
    Useful for testing and debugging.
    """
    logger.info(f"Analyze request from: {request.client.host}")
    
    content = await file.read()
    
    try:
        # Get detailed analysis
        capabilities = receipt_processor.get_processing_capabilities()
        
        # Process with all available methods
        results = {}
        
        # OCR analysis
        if capabilities["capabilities"]["ocr"]:
            ocr_result = receipt_processor.process_image(content, processing_mode="ocr")
            results["ocr"] = ocr_result
        
        # AI analysis
        if capabilities["capabilities"]["ai"]:
            ai_result = receipt_processor.process_image(content, processing_mode="ai")
            results["ai"] = ai_result
        
        # Hybrid analysis
        if "ai-ocr-hybrid" in capabilities["available_modes"]:
            hybrid_result = receipt_processor.process_image(content, processing_mode="auto")
            results["hybrid"] = hybrid_result
        
        return {
            "success": True,
            "message": "レシート分析が完了しました。",
            "capabilities": capabilities,
            "results": results,
            "comparison": _compare_results(results) if detailed else None
        }
        
    except Exception as e:
        logger.error(f"Error analyzing receipt: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"分析中にエラーが発生しました: {str(e)}",
                "data": None
            }
        )

def _compare_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Compare results from different processing methods."""
    comparison = {
        "date_consistency": [],
        "amount_consistency": [],
        "store_name_consistency": []
    }
    
    for method, result in results.items():
        if result.get("success") and result.get("data"):
            data = result["data"]
            comparison["date_consistency"].append({
                "method": method,
                "value": data.get("date")
            })
            comparison["amount_consistency"].append({
                "method": method,
                "value": data.get("total_amount")
            })
            comparison["store_name_consistency"].append({
                "method": method,
                "value": data.get("store_name")
            })
    
    return comparison

@app.get("/api/receipts", response_model=ReceiptList)
async def get_receipts(
    skip: int = Query(0, ge=0, description="Number of receipts to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of receipts to return")
):
    """Get receipts with pagination support."""
    try:
        # Sort by creation date (newest first)
        sorted_receipts = sorted(
            receipts_db, 
            key=lambda x: x.get("created_at", ""), 
            reverse=True
        )
        
        # Apply pagination
        paginated_receipts = sorted_receipts[skip:skip + limit]
        
        logger.info(f"Retrieved {len(paginated_receipts)} receipts (skip={skip}, limit={limit})")
        
        return {
            "receipts": paginated_receipts,
            "total": len(receipts_db),
            "skip": skip,
            "limit": limit
        }
        
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
        
        # Preserve processing info
        if "processing_info" in receipts_db[receipt_index]:
            updated_receipt["processing_info"] = receipts_db[receipt_index]["processing_info"]
        
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

@app.get("/api/receipts/export/csv")
async def export_receipts_csv():
    """Export receipts as CSV."""
    try:
        if not receipts_db:
            raise HTTPException(status_code=404, detail="エクスポートするデータがありません。")
        
        # Create CSV content
        output = io.StringIO()
        
        # Extended fieldnames for more detailed export
        fieldnames = [
            "id", "date", "store_name", "total_amount", 
            "tax_excluded_amount", "tax_included_amount", 
            "expense_category", "payment_method", "items_count",
            "processing_method", "confidence", "created_at", "updated_at"
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        
        # Write header in Japanese
        writer.writerow({
            "id": "ID",
            "date": "日付",
            "store_name": "店名・会社名",
            "total_amount": "合計金額",
            "tax_excluded_amount": "税抜価格",
            "tax_included_amount": "税込価格",
            "expense_category": "費目カテゴリー",
            "payment_method": "支払い方法",
            "items_count": "商品点数",
            "processing_method": "処理方法",
            "confidence": "信頼度",
            "created_at": "作成日時",
            "updated_at": "更新日時"
        })
        
        # Write data rows
        for receipt in sorted(receipts_db, key=lambda x: x.get("created_at", "")):
            row = {
                "id": receipt.get("id", ""),
                "date": receipt.get("date", ""),
                "store_name": receipt.get("store_name", ""),
                "total_amount": receipt.get("total_amount", ""),
                "tax_excluded_amount": receipt.get("tax_excluded_amount", ""),
                "tax_included_amount": receipt.get("tax_included_amount", ""),
                "expense_category": receipt.get("expense_category", ""),
                "payment_method": receipt.get("payment_method", ""),
                "items_count": len(receipt.get("items", [])) if receipt.get("items") else 0,
                "processing_method": receipt.get("processing_info", {}).get("method", ""),
                "confidence": receipt.get("combined_confidence", receipt.get("ai_confidence", receipt.get("ocr_confidence", ""))),
                "created_at": receipt.get("created_at", ""),
                "updated_at": receipt.get("updated_at", "")
            }
            writer.writerow(row)
        
        # Generate CSV content
        csv_content = output.getvalue()
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"receipt_data_{timestamp}.csv"
        
        # Return as streaming response
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8-sig"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting receipts: {e}")
        raise HTTPException(status_code=500, detail="データエクスポート中にエラーが発生しました。")

@app.get("/api/stats")
async def get_statistics():
    """Get enhanced receipt statistics."""
    try:
        if not receipts_db:
            return {
                "total_receipts": 0,
                "total_amount": 0,
                "average_amount": 0,
                "processing_methods": {},
                "expense_categories": {},
                "date_range": None,
                "confidence_stats": {}
            }
        
        total_receipts = len(receipts_db)
        total_amount = sum(r.get("total_amount", 0) for r in receipts_db if r.get("total_amount"))
        average_amount = total_amount / total_receipts if total_receipts > 0 else 0
        
        # Processing methods breakdown
        processing_methods = {}
        for receipt in receipts_db:
            method = receipt.get("processing_info", {}).get("method", "unknown")
            processing_methods[method] = processing_methods.get(method, 0) + 1
        
        # Expense categories breakdown
        expense_categories = {}
        for receipt in receipts_db:
            category = receipt.get("expense_category", "未分類")
            expense_categories[category] = expense_categories.get(category, 0) + 1
        
        # Date range
        dates = [r.get("date") for r in receipts_db if r.get("date")]
        date_range = {
            "earliest": min(dates) if dates else None,
            "latest": max(dates) if dates else None
        }
        
        # Confidence statistics
        confidences = []
        for receipt in receipts_db:
            conf = receipt.get("combined_confidence") or receipt.get("ai_confidence") or receipt.get("ocr_confidence")
            if conf is not None:
                confidences.append(conf)
        
        confidence_stats = {
            "average": sum(confidences) / len(confidences) if confidences else 0,
            "min": min(confidences) if confidences else 0,
            "max": max(confidences) if confidences else 0
        }
        
        return {
            "total_receipts": total_receipts,
            "total_amount": total_amount,
            "average_amount": round(average_amount, 2),
            "processing_methods": processing_methods,
            "expense_categories": expense_categories,
            "date_range": date_range,
            "confidence_stats": confidence_stats
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
            "message": "予期しないエラーが発生しました。",
            "data": None,
            "error_details": str(exc) if settings.debug else None
        }
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info(f"Receipt Scanner API v2.0.0 starting up in {settings.environment} mode")
    
    capabilities = receipt_processor.get_processing_capabilities()
    logger.info(f"Processing mode: {capabilities['processing_mode']}")
    logger.info(f"Available modes: {capabilities['available_modes']}")
    logger.info(f"Capabilities: {capabilities['capabilities']}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed origins: {allowed_origins}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Receipt Scanner API shutting down")
