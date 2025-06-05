export interface ReceiptData {
  id?: number;
  date: string;
  store_name: string;
  total_amount: number;
  tax_excluded_amount?: number | null;
  tax_included_amount?: number | null;
  expense_category?: string | null;
  created_at?: string;
  updated_at?: string;
  processed_with?: string;
}

export interface ReceiptResponse {
  success: boolean;
  message: string;
  data?: ReceiptData | null;
}

export interface ReceiptListResponse {
  success: boolean;
  message: string;
  data?: ReceiptData[] | null;
}

export interface ExportResponse {
  success: boolean;
  message: string;
  data?: {
    csv_data: string;
  } | null;
}

export interface ApiResponse<T = any> {
  success: boolean;
  message: string;
  data: T | null;
}

export interface ReceiptList {
  receipts: ReceiptData[];
}
