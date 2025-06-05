-- レシートテーブル作成
CREATE TABLE IF NOT EXISTS receipts (
    id BIGSERIAL PRIMARY KEY,
    store_name TEXT NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    tax_excluded_amount DECIMAL(10,2),
    tax_included_amount DECIMAL(10,2),
    expense_category TEXT,
    date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RLS (Row Level Security) 有効化
ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;

-- 全ユーザーが読み書きできるポリシー（後で調整可能）
CREATE POLICY "Enable read access for all users" ON receipts FOR SELECT USING (true);
CREATE POLICY "Enable insert access for all users" ON receipts FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable update access for all users" ON receipts FOR UPDATE USING (true);
CREATE POLICY "Enable delete access for all users" ON receipts FOR DELETE USING (true);

-- インデックス作成（パフォーマンス向上）
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date);
CREATE INDEX IF NOT EXISTS idx_receipts_store_name ON receipts(store_name);
CREATE INDEX IF NOT EXISTS idx_receipts_expense_category ON receipts(expense_category);

-- 更新日時の自動更新トリガー
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_receipts_updated_at 
    BEFORE UPDATE ON receipts 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();