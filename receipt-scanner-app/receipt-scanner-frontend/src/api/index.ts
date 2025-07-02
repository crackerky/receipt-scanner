// 画像変換ユーティリティ関数
export async function convertImageToJPEG(file: File): Promise<File> {
  // すでにJPEGまたはPNGの場合はそのまま返す
  if (file.type === 'image/jpeg' || file.type === 'image/png') {
    return file;
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (event) => {
      const img = new Image();
      
      img.onload = () => {
        // Canvasを使用して画像を変換
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
          reject(new Error('Canvas context not available'));
          return;
        }

        // 元の画像サイズを維持（ただし最大4000pxに制限）
        const maxSize = 4000;
        let width = img.width;
        let height = img.height;
        
        if (width > maxSize || height > maxSize) {
          const ratio = Math.min(maxSize / width, maxSize / height);
          width *= ratio;
          height *= ratio;
        }
        
        canvas.width = width;
        canvas.height = height;
        
        // 白背景を設定（透過画像対策）
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, width, height);
        
        // 画像を描画
        ctx.drawImage(img, 0, 0, width, height);
        
        // CanvasをBlobに変換
        canvas.toBlob((blob) => {
          if (blob) {
            // 新しいFileオブジェクトを作成
            const convertedFile = new File(
              [blob], 
              file.name.replace(/\.[^/.]+$/, '.jpg'), // 拡張子を.jpgに変更
              { type: 'image/jpeg' }
            );
            resolve(convertedFile);
          } else {
            reject(new Error('Failed to convert image'));
          }
        }, 'image/jpeg', 0.9); // 品質90%のJPEGとして保存
      };
      
      img.onerror = () => {
        reject(new Error('Failed to load image'));
      };
      
      if (event.target?.result) {
        img.src = event.target.result as string;
      }
    };
    
    reader.onerror = () => {
      reject(new Error('Failed to read file'));
    };
    
    reader.readAsDataURL(file);
  });
}

// HEIC to JPEG converter using heic2any library (optional - more reliable)
export async function convertHEICToJPEG(file: File): Promise<File> {
  // Check if the file might be HEIC
  const isHEIC = file.type === 'image/heic' || 
                 file.type === 'image/heif' || 
                 file.name.toLowerCase().endsWith('.heic') ||
                 file.name.toLowerCase().endsWith('.heif');
  
  if (!isHEIC) {
    return file;
  }

  try {
    // Use the built-in image conversion first
    return await convertImageToJPEG(file);
  } catch (error) {
    console.error('HEIC conversion failed:', error);
    throw new Error('HEIC画像の変換に失敗しました。別の形式の画像をお試しください。');
  }
}

// API設定とエラーハンドリングを強化
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

console.log('API_URL:', API_URL); // デバッグ用

interface ApiResponse<T = any> {
  success: boolean;
  message: string;
  data: T | null;
}

class ApiError extends Error {
  constructor(public status: number, public data: any) {
    super(`API Error: ${status}`);
  }
}

async function apiRequest<T = any>(url: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  try {
    console.log(`API Request: ${options.method || 'GET'} ${url}`); // デバッグ用

    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });

    console.log(`API Response: ${response.status} ${response.statusText}`); // デバッグ用

    if (!response.ok) {
      const errorData = await response.text();
      console.error('API Error Response:', errorData);
      throw new ApiError(response.status, errorData);
    }

    const data = await response.json();
    console.log('API Response Data:', data); // デバッグ用
    
    return data;
  } catch (error) {
    console.error('API Request Failed:', error);
    
    if (error instanceof ApiError) {
      throw error;
    }
    
    // ネットワークエラーやその他のエラー
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error(`バックエンドサーバーに接続できません。${API_URL} が起動しているか確認してください。`);
    }
    
    throw new Error(`予期しないエラーが発生しました: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

export async function uploadReceipt(file: File): Promise<ApiResponse> {
  // ファイル検証
  if (!file) {
    throw new Error('ファイルが選択されていません。');
  }

  console.log('Original file:', {
    name: file.name,
    size: file.size,
    type: file.type
  });

  // 画像をJPEGに変換（必要な場合）
  let processedFile = file;
  
  try {
    // HEICまたは非対応形式の場合、JPEGに変換
    const needsConversion = !['image/jpeg', 'image/png'].includes(file.type) ||
                          file.name.toLowerCase().endsWith('.heic') ||
                          file.name.toLowerCase().endsWith('.heif') ||
                          file.type === 'application/octet-stream';
    
    if (needsConversion) {
      console.log('Converting image to JPEG...');
      processedFile = await convertImageToJPEG(file);
      console.log('Converted file:', {
        name: processedFile.name,
        size: processedFile.size,
        type: processedFile.type
      });
    }
  } catch (conversionError) {
    console.error('Image conversion failed:', conversionError);
    // 変換に失敗しても元のファイルで試してみる
    processedFile = file;
  }

  const maxSize = 50 * 1024 * 1024; // 50MB
  if (processedFile.size > maxSize) {
    throw new Error('ファイルサイズが大きすぎます。50MB以下のファイルを選択してください。');
  }

  const formData = new FormData();
  formData.append('file', processedFile);

  return apiRequest(`${API_URL}/api/receipts/upload`, {
    method: 'POST',
    body: formData,
  });
}

export async function getReceipts(): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/receipts`);
}

export async function deleteReceipt(receiptId: number): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/receipts/${receiptId}`, {
    method: 'DELETE',
  });
}

export async function updateReceipt(receiptId: number, data: any): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/receipts/${receiptId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
}

export async function exportReceipts(): Promise<string> {
  try {
    const response = await fetch(`${API_URL}/api/receipts/export/csv`, {
      method: 'GET',
      headers: {
        'Accept': 'text/csv',
      },
    });

    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }

    // Get the CSV content directly from the response
    const csvContent = await response.text();
    return csvContent;
  } catch (error) {
    console.error('Export error:', error);
    throw error;
  }
}

export async function testUploadReceipt(): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/receipts/test`, {
    method: 'POST',
  });
}

// ヘルスチェック関数を追加
export async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/healthz`, {
      method: 'GET',
      timeout: 5000
    } as RequestInit);
    
    return response.ok;
  } catch (error) {
    console.error('Health check failed:', error);
    return false;
  }
}

// API状態確認関数を追加
export async function getApiStatus(): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/status`);
}

// レシート画像を取得する関数を追加
export function getReceiptImageUrl(receiptId: number): string {
  return `${API_URL}/api/receipts/${receiptId}/image`;
}
