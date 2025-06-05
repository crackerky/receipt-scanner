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

  const allowedTypes = ['image/jpeg', 'image/png', 'image/jpg'];
  if (!allowedTypes.includes(file.type)) {
    throw new Error('サポートされていないファイル形式です。JPEG または PNG ファイルを選択してください。');
  }

  const maxSize = 10 * 1024 * 1024; // 10MB
  if (file.size > maxSize) {
    throw new Error('ファイルサイズが大きすぎます。10MB以下のファイルを選択してください。');
  }

  console.log('Uploading file:', {
    name: file.name,
    size: file.size,
    type: file.type
  });

  const formData = new FormData();
  formData.append('file', file);

  return apiRequest(`${API_URL}/api/receipts/upload`, {
    method: 'POST',
    body: formData,
  });
}

export async function getReceipts(): Promise<ApiResponse> {
  return apiRequest(`${API_URL}/api/receipts`);
}

export async function exportReceipts(): Promise<string> {
  const response = await apiRequest(`${API_URL}/api/receipts/export`);
  return response.data?.csv_data || response.csv_data || '';
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