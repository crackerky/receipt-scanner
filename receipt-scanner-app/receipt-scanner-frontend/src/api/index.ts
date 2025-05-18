const API_URL = import.meta.env.VITE_API_URL;

export async function uploadReceipt(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/api/receipts/upload`, {
    method: 'POST',
    body: formData,
  });

  return response.json();
}

export async function getReceipts(): Promise<any> {
  const response = await fetch(`${API_URL}/api/receipts`);
  return response.json();
}

export async function exportReceipts(): Promise<string> {
  const response = await fetch(`${API_URL}/api/receipts/export`);
  const data = await response.json();
  return data.csv_data;
}

export async function testUploadReceipt(): Promise<any> {
  const response = await fetch(`${API_URL}/api/receipts/test`, {
    method: 'POST',
  });
  return response.json();
}