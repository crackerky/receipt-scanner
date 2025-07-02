import logging
import time
from functools import wraps
from typing import Dict, Any, List, Optional
import io
import csv
import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
import psycopg

from app.config import settings
from app.models import ReceiptData, ReceiptResponse, ReceiptList
from app.receipt_processor import ReceiptProcessor
from app.database import get_db, engine, Base
from app.db_models import Receipt as ReceiptDB, User
from app.auth import get_current_active_user, get_current_active_user_optional
from app.auth_routes import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Receipt Scanner API",
    description="Secure receipt scanning and processing API with AI-OCR hybrid and Vision API support",
    version="2.2.0",
    debug=settings.debug
)

# Include authentication routes
app.include_router(auth_router)

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

# Create receipts_images directory for storing uploaded images
UPLOAD_DIR = Path("receipts_images")
UPLOAD_DIR.mkdir(exist_ok=True)

# Create database tables on startup
Base.metadata.create_all(bind=engine)

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
        "version": "2.1.0",
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
        "api_version": "2.1.0",
        "environment": settings.environment,
        "features": {
            "openai_processing": capabilities["capabilities"]["ai"],
            "ocr_processing": capabilities["capabilities"]["ocr"],
            "vision_api": capabilities["capabilities"]["vision"],
            "ai_ocr_hybrid": "ai-ocr-hybrid" in capabilities["available_modes"],
            "rate_limiting": True,
            "heic_support": capabilities["capabilities"]["heic_support"],
            "advanced_image_processing": capabilities["capabilities"]["advanced_image_processing"]
        },
        "processing_mode": capabilities["processing_mode"],
        "available_modes": capabilities["available_modes"],
        "recommended_mode": capabilities["recommended_mode"],
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
    processing_mode: Optional[str] = Query(None, description="Processing mode: 'ai', 'ocr', 'vision', or 'auto'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """
    Upload and process a receipt image.
    
    Processing modes:
    - 'vision': Use OpenAI Vision API (highest accuracy, requires OpenAI API)
    - 'ai': Use AI with OCR text (requires OpenAI API)
    - 'ocr': Use only OCR processing
    - 'auto' or None: Automatically select best available mode
    """
    
    logger.info(f"Upload request from: {request.client.host}")
    logger.info(f"Processing mode requested: {processing_mode}")
    logger.info(f"File info: name={file.filename}, content_type={file.content_type}")
    
    # Validate processing mode
    if processing_mode and processing_mode not in ["ai", "ocr", "vision", "auto"]:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "無効な処理モードです。'ai', 'ocr', 'vision', または 'auto' を指定してください。",
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
            receipt_data = result["data"]
            
            # Create database record
            db_receipt = ReceiptDB(
                store_name=receipt_data.get("store_name", "Unknown"),
                purchase_date=receipt_data.get("date", datetime.utcnow()),
                total_amount=receipt_data.get("total_amount", 0.0),
                category=receipt_data.get("expense_category"),
                items=receipt_data.get("items"),
                payment_method=receipt_data.get("payment_method"),
                tax_amount=receipt_data.get("tax_amount"),
                processing_mode=result.get("processing_mode", processing_mode or "auto"),
                confidence_score=result.get("confidence_score"),
                ocr_text=result.get("ocr_text"),
                user_id=current_user.id
            )
            
            # Save image file
            if content:
                image_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
                image_path = UPLOAD_DIR / image_filename
                with open(image_path, "wb") as f:
                    f.write(content)
                db_receipt.image_path = str(image_path)
            
            # Save to database
            db.add(db_receipt)
            db.commit()
            db.refresh(db_receipt)
            
            # Update result with database ID
            receipt_data["id"] = db_receipt.id
            receipt_data["created_at"] = db_receipt.created_at.isoformat() if db_receipt.created_at else None
            receipt_data["image_path"] = db_receipt.image_path
            
            logger.info(f"Successfully processed and saved receipt {db_receipt.id}")
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
    detailed: bool = Query(False, description="Return detailed analysis"),
    current_user: User = Depends(get_current_active_user_optional)
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
        
        # Vision API analysis
        if capabilities["capabilities"]["vision"]:
            vision_result = receipt_processor.process_image(content, processing_mode="vision")
            results["vision"] = vision_result
        
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
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of receipts to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Get receipts with pagination support."""
    try:
        # Query receipts from database (only user's receipts)
        query = db.query(ReceiptDB).filter(
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        )
        total = query.count()
        
        # Sort by creation date (newest first) and apply pagination
        receipts = query.order_by(ReceiptDB.created_at.desc()).offset(skip).limit(limit).all()
        
        # Convert to response format
        receipts_data = [receipt.to_dict() for receipt in receipts]
        
        logger.info(f"Retrieved {len(receipts)} receipts (skip={skip}, limit={limit})")
        
        return {
            "receipts": receipts_data,
            "total": total,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error retrieving receipts: {e}")
        raise HTTPException(status_code=500, detail="レシート一覧の取得中にエラーが発生しました。")

@app.get("/api/receipts/{receipt_id}")
async def get_receipt(
    receipt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Get a specific receipt by ID."""
    try:
        receipt = db.query(ReceiptDB).filter(
            ReceiptDB.id == receipt_id, 
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).first()
        if not receipt:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        return {"receipt": receipt.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="レシート取得中にエラーが発生しました。")

@app.put("/api/receipts/{receipt_id}")
async def update_receipt(
    receipt_id: int, 
    receipt_data: ReceiptData, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Update a specific receipt."""
    try:
        receipt = db.query(ReceiptDB).filter(
            ReceiptDB.id == receipt_id, 
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).first()
        if not receipt:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        # Update receipt data
        update_data = receipt_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(receipt, field):
                setattr(receipt, field, value)
        
        receipt.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(receipt)
        
        return {
            "success": True,
            "message": "レシート情報を更新しました。",
            "data": receipt.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating receipt {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="レシート更新中にエラーが発生しました。")

@app.delete("/api/receipts/{receipt_id}")
async def delete_receipt(
    receipt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Delete a specific receipt."""
    try:
        receipt = db.query(ReceiptDB).filter(
            ReceiptDB.id == receipt_id, 
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).first()
        if not receipt:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        # Soft delete
        receipt.is_deleted = True
        db.commit()
        
        # Delete image file if exists
        if receipt.image_path and os.path.exists(receipt.image_path):
            try:
                os.remove(receipt.image_path)
            except Exception as e:
                logger.warning(f"Failed to delete image file: {e}")
        
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
async def export_receipts_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Export receipts as CSV."""
    try:
        receipts = db.query(ReceiptDB).filter(
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).order_by(ReceiptDB.created_at.desc()).all()
        if not receipts:
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
        for receipt in receipts:
            row = {
                "id": receipt.id,
                "date": receipt.purchase_date.strftime("%Y-%m-%d") if receipt.purchase_date else "",
                "store_name": receipt.store_name or "",
                "total_amount": receipt.total_amount or 0,
                "tax_excluded_amount": "",  # Not stored separately in DB
                "tax_included_amount": receipt.total_amount or 0,
                "expense_category": receipt.category or "",
                "payment_method": receipt.payment_method or "",
                "items_count": len(receipt.items) if receipt.items else 0,
                "processing_method": receipt.processing_mode or "",
                "confidence": receipt.confidence_score or "",
                "created_at": receipt.created_at.strftime("%Y-%m-%d %H:%M:%S") if receipt.created_at else "",
                "updated_at": receipt.updated_at.strftime("%Y-%m-%d %H:%M:%S") if receipt.updated_at else ""
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
async def get_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Get enhanced receipt statistics."""
    try:
        receipts = db.query(ReceiptDB).filter(
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).all()
        
        if not receipts:
            return {
                "total_receipts": 0,
                "total_amount": 0,
                "average_amount": 0,
                "processing_methods": {},
                "expense_categories": {},
                "date_range": None,
                "confidence_stats": {}
            }
        
        total_receipts = len(receipts)
        total_amount = sum(r.total_amount for r in receipts if r.total_amount)
        average_amount = total_amount / total_receipts if total_receipts > 0 else 0
        
        # Processing methods breakdown
        processing_methods = {}
        for receipt in receipts:
            method = receipt.processing_mode or "unknown"
            processing_methods[method] = processing_methods.get(method, 0) + 1
        
        # Expense categories breakdown
        expense_categories = {}
        for receipt in receipts:
            category = receipt.category or "未分類"
            expense_categories[category] = expense_categories.get(category, 0) + 1
        
        # Date range
        dates = [r.purchase_date for r in receipts if r.purchase_date]
        date_range = {
            "earliest": min(dates).strftime("%Y-%m-%d") if dates else None,
            "latest": max(dates).strftime("%Y-%m-%d") if dates else None
        }
        
        # Confidence statistics
        confidences = []
        for receipt in receipts:
            if receipt.confidence_score is not None:
                confidences.append(receipt.confidence_score)
        
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

@app.get("/api/receipts/{receipt_id}/image")
async def get_receipt_image(
    receipt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_optional)
):
    """Get the original image for a receipt."""
    try:
        receipt = db.query(ReceiptDB).filter(
            ReceiptDB.id == receipt_id, 
            ReceiptDB.is_deleted == False,
            ReceiptDB.user_id == current_user.id
        ).first()
        if not receipt:
            raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
        
        if not receipt.image_path or not os.path.exists(receipt.image_path):
            raise HTTPException(status_code=404, detail="レシート画像が見つかりません。")
        
        return FileResponse(
            receipt.image_path,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename=receipt_{receipt_id}.jpg"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving receipt image {receipt_id}: {e}")
        raise HTTPException(status_code=500, detail="画像取得中にエラーが発生しました。")

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
    logger.info(f"Receipt Scanner API v2.1.0 starting up in {settings.environment} mode")
    
    capabilities = receipt_processor.get_processing_capabilities()
    logger.info(f"Processing mode: {capabilities['processing_mode']}")
    logger.info(f"Available modes: {capabilities['available_modes']}")
    logger.info(f"Capabilities: {capabilities['capabilities']}")
    logger.info(f"Recommended mode: {capabilities['recommended_mode']}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed origins: {allowed_origins}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Receipt Scanner API shutting down")
