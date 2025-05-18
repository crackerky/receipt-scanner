import { ReceiptResponse, ReceiptList } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const uploadReceipt = async (file: File): Promise<ReceiptResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch(`${API_URL}/api/receipts/upload`, {
      method: 'POST',
      body: formData,
    });

    return await response.json();
  } catch (error) {
    return {
      success: false,
      message: '通信エラーが発生しました。ネットワーク接続を確認してください。',
    };
  }
};

export const getReceipts = async (): Promise<ReceiptList> => {
  try {
    const response = await fetch(`${API_URL}/api/receipts`);
    return await response.json();
  } catch (error) {
    return { receipts: [] };
  }
};

export const exportReceipts = async (): Promise<string> => {
  try {
    const response = await fetch(`${API_URL}/api/receipts/export`);
    const data = await response.json();
    return data.csv_data;
  } catch (error) {
    throw new Error('CSVエクスポート中にエラーが発生しました。');
  }
};

export const clearReceipts = async (): Promise<{ message: string }> => {
  try {
    const response = await fetch(`${API_URL}/api/receipts`, {
      method: 'DELETE',
    });
    return await response.json();
  } catch (error) {
    return { message: 'データ削除中にエラーが発生しました。' };
  }
};

export const testUploadReceipt = async (): Promise<ReceiptResponse> => {
  try {
    const response = await fetch(`${API_URL}/api/receipts/test`, {
      method: 'POST',
    });
    return await response.json();
  } catch (error) {
    return {
      success: false,
      message: '通信エラーが発生しました。ネットワーク接続を確認してください。',
    };
  }
};
