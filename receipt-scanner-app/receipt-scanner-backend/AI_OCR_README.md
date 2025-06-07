# AI-OCR Vision API Feature

This branch adds support for OpenAI's Vision API (GPT-4o) for advanced OCR capabilities.

## Features

- **AI-OCR with GPT-4o Vision**: Direct image analysis without traditional OCR
- **Automatic fallback**: If Vision API fails, falls back to Tesseract OCR
- **Better accuracy**: Handles handwritten text, poor quality images, and complex layouts
- **Multi-language support**: Works with Japanese and English receipts

## Configuration

Add these environment variables to enable Vision API:

```bash
# Enable/disable Vision API (default: true)
USE_VISION_API=true

# Vision API model (options: gpt-4o, gpt-4o-mini)
VISION_API_MODEL=gpt-4o

# Your existing OpenAI API key
OPENAI_API_KEY=sk-your-api-key
```

## How it works

1. **Image Upload**: User uploads a receipt image
2. **Vision API Processing**: 
   - Image is encoded to base64
   - Sent to GPT-4o Vision API with structured prompt
   - AI directly extracts receipt information
3. **Fallback**: If Vision API fails, uses traditional OCR pipeline:
   - Tesseract OCR → Text extraction → GPT-3.5 analysis → Regex patterns

## Cost Considerations

- **GPT-4o**: $5.00 per 1M input tokens, $20.00 per 1M output tokens
- **GPT-4o-mini**: $0.15 per 1M input tokens, $0.60 per 1M output tokens
- Average receipt image uses 500-2000 tokens (high detail)

## Testing

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export USE_VISION_API=true
export VISION_API_MODEL=gpt-4o
export OPENAI_API_KEY=your-key
```

3. Run the application:
```bash
uvicorn app.main:app --reload
```

4. Test with various receipt images:
   - Clear printed receipts
   - Handwritten receipts
   - Blurry or low-quality images
   - Complex layouts with tables

## Performance

Vision API provides:
- Better accuracy for difficult images
- Direct extraction without OCR errors
- Structured data output
- Support for various image formats

## Deployment

For Railway deployment, add the environment variables in the Railway dashboard:
- `USE_VISION_API=true`
- `VISION_API_MODEL=gpt-4o` (or `gpt-4o-mini` for cost savings)

The feature is backward compatible - if Vision API is disabled or fails, it automatically falls back to the traditional OCR pipeline.
