export interface ReceiptData {
  id?: number;
  date: string;
  store_name: string;
  total_amount: number;
  tax_excluded_amount?: number | null;
  tax_included_amount?: number | null;
  expense_category?: string | null;
}

export interface ReceiptResponse {
  success: boolean;
  message: string;
  data?: ReceiptData | null;
}

export interface ReceiptList {
  receipts: ReceiptData[];
}
